"""C struct table parser — reads struct array initializers from .c/.h files.

Handles complex embedded-style constant tables like:

    static const MyStruct LUT[COUNT] = {
        /* Label1 */ {{val1, val2}, val3, ...},
        /* Label2 */ {{val1, val2}, val3, ...},
    };

Features:
  - Extracts row labels from leading comments (/* Label */)
  - Parses nested brace initializers with field mapping
  - Handles #if/#elif/#endif conditional blocks (extracts active variant)
  - Supports C float suffixes (1.0F), hex literals (0xFF), unsigned (5u)
  - Preserves computed expressions as string constants (e.g., "0.25F / NF_PSC_FREQUENCY")
  - Separates literal numeric values from expression-based values

Configuration (in .consync.yaml):
    source_format: c_struct_table
    parser_options:
      fields: [R_Phase, L_d, L_q, Psi, J, Imax, Tmax, NPpair]
      variant: DPB          # selects #elif block (matches RBFS_PscMotorParameter_DPB)
      table_var: PSC_HWVarParLUT   # variable name of the struct array
"""

from __future__ import annotations

import re
from pathlib import Path

from consync.models import Constant
from consync.parsers import register


# Regex to match row labels in comments like /* BWA NI S4 */ or /* EMB 12V 35KN */
_ROW_LABEL_RE = re.compile(r"/\*\s*(.+?)\s*\*/")

# Regex to match a C numeric literal (int or float, with optional suffix)
_NUMERIC_LITERAL_RE = re.compile(
    r"^[+-]?"
    r"(?:0[xX][0-9a-fA-F]+|"        # hex
    r"\d+\.?\d*(?:[eE][+-]?\d+)?)"   # decimal / float / scientific
    r"[fFlLuU]*$"                     # C type suffixes
)

# Regex to detect #if / #elif lines with variant names
_PREPROC_IF_RE = re.compile(
    r"^\s*#\s*(?:el)?if\s*\(.*?==\s*(\w+)\s*\)"
)
_PREPROC_ENDIF_RE = re.compile(r"^\s*#\s*endif")
_PREPROC_ELIF_RE = re.compile(r"^\s*#\s*elif")

# Matches the start of a static const struct array declaration
_TABLE_DECL_RE = re.compile(
    r"^\s*(?:static\s+)?(?:const\s+)?\w+\s+(\w+)\s*\["
)


def _strip_c_suffix(token: str) -> str:
    """Strip C numeric literal suffixes like F, f, L, u, U.

    Does NOT strip from hex literals (0x...) since hex digits overlap with suffixes.
    """
    t = token.strip()
    # Don't strip from hex — 'F' is a valid hex digit
    if t.startswith(("0x", "0X", "+0x", "+0X", "-0x", "-0X")):
        return t
    return t.rstrip("fFlLuU")


def _is_numeric_literal(token: str) -> bool:
    """Check if a token is a plain C numeric literal (not an expression)."""
    stripped = _strip_c_suffix(token.strip())
    return bool(_NUMERIC_LITERAL_RE.match(stripped))


def _parse_numeric(token: str) -> float | int:
    """Parse a C numeric literal to Python number."""
    stripped = _strip_c_suffix(token.strip())
    if stripped.startswith(("0x", "0X")):
        return int(stripped, 16)
    if "." in stripped or "e" in stripped.lower():
        return float(stripped)
    return int(stripped)


def _tokenize_brace_values(text: str) -> list[str]:
    """Tokenize a brace-enclosed initializer into top-level values.

    Handles nested braces: {1.0, {2.0, 3.0}, 4.0} → ['1.0', '{2.0, 3.0}', '4.0']
    """
    tokens: list[str] = []
    depth = 0
    current = ""

    for ch in text:
        if ch == "{":
            if depth > 0:
                current += ch
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth > 0:
                current += ch
            elif depth == 0 and current.strip():
                tokens.append(current.strip())
                current = ""
        elif ch == "," and depth == 1:
            if current.strip():
                tokens.append(current.strip())
            current = ""
        else:
            if depth >= 1:
                current += ch

    # Handle remaining (for cases without trailing comma)
    if current.strip():
        tokens.append(current.strip())

    return tokens


def _flatten_values(text: str) -> list[str]:
    """Recursively flatten nested brace initializers into a flat list of scalar values.

    Input is the raw content INSIDE the outermost braces.
    {1.0, {2.0, 3.0}, 4.0} → ['1.0', '2.0', '3.0', '4.0']
    Scalars at any depth are collected. Sub-braces are recursed into.
    """
    # Tokenize at the current level (comma-separated, respecting brace depth)
    tokens = _tokenize_at_level(text)
    result: list[str] = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if t.startswith("{"):
            # Recurse into the brace content
            inner = t[1:-1] if t.endswith("}") else t[1:]
            result.extend(_flatten_values(inner))
        else:
            result.append(t)
    return result


def _tokenize_at_level(text: str) -> list[str]:
    """Split text by commas, respecting nested braces.

    Returns tokens at the current level — brace groups are kept as single tokens.
    """
    tokens: list[str] = []
    depth = 0
    current = ""

    for ch in text:
        if ch == "{":
            depth += 1
            current += ch
        elif ch == "}":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            if current.strip():
                tokens.append(current.strip())
            current = ""
        else:
            current += ch

    if current.strip():
        tokens.append(current.strip())

    return tokens


def _extract_row_data(line: str) -> tuple[str, str] | None:
    """Extract (label, brace_content) from a struct initializer row.

    Returns None if line doesn't look like a struct row.
    The brace_content is the inner content of the outermost balanced braces.
    """
    # Try to find a label comment
    label_match = _ROW_LABEL_RE.search(line)
    label = label_match.group(1).strip() if label_match else ""

    # Find the first { that starts the struct data
    brace_start = line.find("{")
    if brace_start == -1:
        return None

    # Find the matching closing brace by counting depth
    data_portion = line[brace_start:]
    depth = 0
    end_idx = -1
    for i, ch in enumerate(data_portion):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx == -1:
        return None

    # Extract the balanced content (strip outermost { })
    inner_content = data_portion[1:end_idx]
    return (label, inner_content)


def _auto_detect_table_var(text: str) -> str | None:
    """Auto-detect the struct array variable name from the file.

    Looks for patterns like:
        static const MyType VarName[SIZE] = {
    Returns the variable name or None.
    """
    for line in text.splitlines():
        m = _TABLE_DECL_RE.match(line)
        if m and "=" in line:
            return m.group(1)
    return None


# Regex for field header comment: /* field1  field2  field3 ... */
_FIELD_HEADER_RE = re.compile(
    r"/\*[\s,]*((?:[A-Za-z_]\w*[\s,]+)+[A-Za-z_]\w*)\s*\*/"
)


def _auto_detect_fields(text: str) -> list[str] | None:
    """Auto-detect field names from the column header comment.

    Looks for a comment line like:
        /*  R_Phase  L_d  L_q  Psi  J  Imax ... */
    that appears just before the first data row (line with {{ ).

    Returns list of field names or None.
    """
    lines = text.splitlines()
    prev_comment = None

    for line in lines:
        stripped = line.strip()
        # Look for comment lines that could be field headers
        if stripped.startswith("/*") and stripped.endswith("*/") and "{{" not in stripped:
            # Extract content between /* and */
            inner = stripped[2:-2].strip()
            # Must contain multiple words separated by whitespace/commas (field names)
            # Filter: must have at least 3 words and no sentences (no spaces within words)
            tokens = re.split(r"[\s,]+", inner)
            tokens = [t for t in tokens if t and re.match(r"^[A-Za-z_]\w*$", t)]
            if len(tokens) >= 3:
                prev_comment = tokens
        # When we hit a data row, the previous comment was the header
        elif "{{" in stripped and prev_comment:
            return prev_comment

    return None


def _auto_detect_variants(text: str) -> list[str]:
    """Find all preprocessor variant names for the primary #if chain in the file.

    Groups by the macro being tested (e.g. RBFS_PscMotorParameter) and returns
    the short variant names from the chain with the most alternatives.
    This avoids picking up unrelated #if blocks (feature flags, etc.)

    Returns list like ['BWA', 'EMB', 'DPB', 'IPB2'].
    """
    # Regex that captures both the macro name and the value it's compared against
    _MACRO_VARIANT_RE = re.compile(
        r"^\s*#\s*(?:el)?if\s*\(\s*(\w+)\s*==\s*(\w+)\s*\)"
    )

    # Group by macro name → list of (full_value, short_name)
    macro_groups: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = _MACRO_VARIANT_RE.match(line)
        if m:
            macro_name = m.group(1)  # e.g. RBFS_PscMotorParameter
            full_value = m.group(2)  # e.g. RBFS_PscMotorParameter_DPB
            short = full_value.rsplit("_", 1)[-1] if "_" in full_value else full_value
            if macro_name not in macro_groups:
                macro_groups[macro_name] = []
            if short not in macro_groups[macro_name]:
                macro_groups[macro_name].append(short)

    if not macro_groups:
        return []

    # Return variants from the chain with the most alternatives (the product switch)
    primary_chain = max(macro_groups.values(), key=len)
    return primary_chain


def _find_variant_block(text: str, variant: str) -> str | None:
    """Find the code block for a specific preprocessor variant.

    Given variant="DPB", finds the block after #elif (...== RBFS_PscMotorParameter_DPB)
    until the next #elif or #endif.
    """
    lines = text.splitlines()
    in_target_block = False
    block_lines: list[str] = []

    for line in lines:
        if in_target_block:
            # Check if we've hit the next #elif or #endif
            if _PREPROC_ELIF_RE.match(line) or _PREPROC_ENDIF_RE.match(line):
                break
            block_lines.append(line)
        else:
            # Check if this is our target #if/#elif
            m = _PREPROC_IF_RE.match(line)
            if m:
                block_name = m.group(1)
                # Match against the variant name (e.g., "DPB" matches "RBFS_PscMotorParameter_DPB")
                if variant.upper() in block_name.upper():
                    in_target_block = True

    return "\n".join(block_lines) if block_lines else None


def _find_table_block(text: str, table_var: str | None = None) -> str | None:
    """Find the struct array declaration block.

    If table_var is given, look for that specific variable name.
    Otherwise find the first static const array declaration.
    """
    lines = text.splitlines()
    in_table = False
    brace_depth = 0
    block_lines: list[str] = []

    for line in lines:
        if not in_table:
            if table_var:
                if table_var in line and "[" in line:
                    in_table = True
            else:
                m = _TABLE_DECL_RE.match(line)
                if m:
                    in_table = True

            if in_table:
                # Find the opening brace
                if "{" in line:
                    brace_depth += line.count("{") - line.count("}")
                    block_lines.append(line)
                continue

        if in_table:
            block_lines.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                break

    return "\n".join(block_lines) if block_lines else None


@register("c_struct_table")
def parse_c_struct_table(
    filepath: str | Path,
    fields: list[str] | None = None,
    variant: str | None = None,
    table_var: str | None = None,
    **kwargs,
) -> list[Constant]:
    """Parse constants from a C struct array initializer table.

    Args:
        filepath: Path to the .c/.h file.
        fields: Ordered list of field names matching the struct layout.
                If not provided, auto-detected from column header comments,
                or falls back to field_0, field_1, etc.
        variant: Preprocessor variant to extract (e.g., "DPB", "EMB", "BWA").
                 Use "all" to extract ALL variants (for multi-sheet output).
                 Matches against #if/#elif conditions.
                 If the file has #if blocks and no variant is given, uses the
                 first variant found.
        table_var: Name of the struct array variable to find.
                   If not provided, auto-detected from the first
                   `static const ... NAME[...] = {` declaration.

    Returns:
        List of Constant objects with names like "RowLabel__FieldName".
        When variant="all", each Constant has metadata["variant"] set.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"C struct table file not found: {filepath}")

    text = filepath.read_text(encoding="utf-8")

    # --- Auto-detection ---
    # Auto-detect table_var if not provided
    if not table_var:
        table_var = _auto_detect_table_var(text)

    # Handle "all" variant mode — parse every variant
    if variant and variant.lower() == "all":
        return _parse_all_variants(text, table_var, fields)

    # Auto-detect variant if file has #if blocks and none specified
    if not variant:
        available_variants = _auto_detect_variants(text)
        if available_variants:
            variant = available_variants[0]  # Default to first variant

    # Strategy: First find the table block, THEN find the variant within it.
    # This handles files where #if/#elif blocks are INSIDE the array declaration.
    working_text = text

    # Step 1: Find the table block (struct array declaration)
    if table_var:
        table_block = _find_table_block(working_text, table_var)
        if table_block:
            working_text = table_block

    # Step 2: Within the table (or full text), find the variant block
    if variant:
        block = _find_variant_block(working_text, variant)
        if block is None:
            # Fallback: try searching in full text (variant block wraps the table)
            block = _find_variant_block(text, variant)
        if block is None:
            raise ValueError(
                f"Variant '{variant}' not found in {filepath}. "
                f"Available variants: {_auto_detect_variants(text)}"
            )
        working_text = block

    # If we still haven't narrowed it down, try finding table in the variant block
    if table_var and variant:
        inner_table = _find_table_block(working_text, table_var)
        if inner_table:
            working_text = inner_table

    # Auto-detect fields from header comment (if not provided)
    if not fields:
        fields = _auto_detect_fields(working_text)
        # If not found in variant block, try full table block or text
        if not fields and table_var:
            table_block = _find_table_block(text, table_var)
            if table_block:
                fields = _auto_detect_fields(table_block)
        if not fields:
            fields = _auto_detect_fields(text)

    constants: list[Constant] = _parse_rows(working_text, fields)

    # Tag each constant with the variant name
    if variant:
        for c in constants:
            c.metadata["variant"] = variant

    return constants


def _parse_all_variants(
    text: str, table_var: str | None, fields: list[str] | None
) -> list[Constant]:
    """Parse ALL variants from the file. Each constant gets metadata['variant']."""
    available_variants = _auto_detect_variants(text)
    if not available_variants:
        # No variants — just parse the whole file
        working_text = text
        if table_var:
            table_block = _find_table_block(working_text, table_var)
            if table_block:
                working_text = table_block
        if not fields:
            fields = _auto_detect_fields(working_text) or _auto_detect_fields(text)
        return _parse_rows(working_text, fields)

    # Auto-detect fields once (from first variant or table header)
    if not fields:
        # Try finding in table block
        if table_var:
            table_block = _find_table_block(text, table_var)
            if table_block:
                fields = _auto_detect_fields(table_block)
        if not fields:
            fields = _auto_detect_fields(text)

    all_constants: list[Constant] = []
    for v in available_variants:
        # Find variant block within the table
        working_text = text
        if table_var:
            table_block = _find_table_block(working_text, table_var)
            if table_block:
                working_text = table_block

        block = _find_variant_block(working_text, v)
        if block is None:
            block = _find_variant_block(text, v)
        if block is None:
            continue

        constants = _parse_rows(block, fields)
        # Tag each with variant
        for c in constants:
            c.metadata["variant"] = v
        all_constants.extend(constants)

    return all_constants


def _parse_rows(text: str, fields: list[str] | None) -> list[Constant]:
    """Parse struct initializer rows from a block of text."""
    constants: list[Constant] = []
    row_counter = 0

    for line in text.splitlines():
        # Skip preprocessor directives, blank lines, and pure comments
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if stripped.startswith("/*") and stripped.endswith("*/") and "{{" not in stripped:
            continue
        # Skip lines that are just opening/closing braces for the array
        if stripped in ("{", "}", "};", "{}", "},"):
            continue
        # Skip table declaration line
        if _TABLE_DECL_RE.match(stripped):
            continue
        # Skip #define lines (SPEEDPARAM macros etc.)
        if stripped.startswith("#define"):
            continue

        row_data = _extract_row_data(line)
        if row_data is None:
            continue

        label, brace_content = row_data

        # Flatten all values from nested braces
        flat_values = _flatten_values(brace_content)

        if not flat_values:
            continue

        # Sanitize label for use as name prefix
        name_prefix = _sanitize_label(label) if label else f"row_{row_counter}"
        row_counter += 1

        # Map values to field names
        for i, raw_val in enumerate(flat_values):
            field_name = fields[i] if fields and i < len(fields) else f"field_{i}"
            const_name = f"{name_prefix}__{field_name}"

            # Determine if value is a literal number or an expression
            raw_val_trimmed = raw_val.strip()

            # Handle boolean-like values (must check before macro detection)
            if raw_val_trimmed.upper() in ("TRUE", "FALSE"):
                constants.append(Constant(
                    name=const_name,
                    value=raw_val_trimmed,
                    unit="",
                    description=f"Row: {label}, Field: {field_name}",
                    metadata={"row_label": label, "field": field_name, "field_index": i,
                              "is_expression": False},
                ))
                continue

            # Skip macro references like SPEEDPARAM, SPEEDPARAM_SIZEM1
            if re.match(r"^[A-Z_][A-Z0-9_]*$", raw_val_trimmed) and not raw_val_trimmed.isdigit():
                constants.append(Constant(
                    name=const_name,
                    value=raw_val_trimmed,
                    unit="",
                    description=f"Row: {label}, Field: {field_name} [macro]",
                    metadata={"row_label": label, "field": field_name, "field_index": i,
                              "is_expression": True, "raw": raw_val_trimmed},
                ))
                continue

            if _is_numeric_literal(raw_val_trimmed):
                value = _parse_numeric(raw_val_trimmed)
                constants.append(Constant(
                    name=const_name,
                    value=value,
                    unit="",
                    description=f"Row: {label}, Field: {field_name}",
                    metadata={"row_label": label, "field": field_name, "field_index": i,
                              "is_expression": False, "raw": raw_val_trimmed},
                ))
            else:
                # Expression-based value — store as string
                constants.append(Constant(
                    name=const_name,
                    value=raw_val_trimmed,
                    unit="",
                    description=f"Row: {label}, Field: {field_name} [expression]",
                    metadata={"row_label": label, "field": field_name, "field_index": i,
                              "is_expression": True, "raw": raw_val_trimmed},
                ))

    return constants


def _sanitize_label(label: str) -> str:
    """Convert a row label to a valid C-style identifier prefix.

    "BWA NI S4" → "BWA_NI_S4"
    "EMB 12V 35KN" → "EMB_12V_35KN"
    """
    # Replace non-alphanumeric chars with underscore
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip())
    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")
    return sanitized
