"""Validation hooks — user-defined checks on constant values.

Validators are defined in .consync.yaml:

    mappings:
      - source: calibration.xlsx
        target: config.h
        validators:
          BRAKE_MAX_PRESSURE:
            min: 0
            max: 300
          TIMEOUT_MS:
            type: int
            min: 100
            max: 60000
          DEVICE_NAME:
            pattern: "^[A-Z]{3}-\\d{4}$"
          LOOKUP_TABLE:
            min_length: 1
            max_length: 256

Supported checks:
  - min / max — numeric range (inclusive)
  - type — "int", "float", "string"
  - pattern — regex pattern for string values
  - min_length / max_length — for arrays or strings
  - not_empty — value must not be "" or []
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from consync.models import Constant

logger = logging.getLogger(__name__)


@dataclass
class ValidationRule:
    """A single validation rule for a constant."""

    name: str  # constant name this rule applies to
    min: float | None = None
    max: float | None = None
    type: str | None = None  # "int", "float", "string"
    pattern: str | None = None  # regex for string values
    min_length: int | None = None
    max_length: int | None = None
    not_empty: bool = False


@dataclass
class ValidationError:
    """A validation failure."""

    constant_name: str
    rule: str
    message: str


@dataclass
class ValidationResult:
    """Aggregate result of running all validators."""

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def parse_validators(raw: dict[str, dict[str, Any]]) -> list[ValidationRule]:
    """Parse validator config from YAML mapping.

    Args:
        raw: Dict of {constant_name: {rule_key: value, ...}}

    Returns:
        List of ValidationRule objects.
    """
    rules = []
    for name, checks in raw.items():
        rule = ValidationRule(
            name=name,
            min=checks.get("min"),
            max=checks.get("max"),
            type=checks.get("type"),
            pattern=checks.get("pattern"),
            min_length=checks.get("min_length"),
            max_length=checks.get("max_length"),
            not_empty=checks.get("not_empty", False),
        )
        rules.append(rule)
    return rules


def validate_constants(
    constants: list[Constant],
    rules: list[ValidationRule],
) -> ValidationResult:
    """Validate a list of constants against rules.

    Args:
        constants: Parsed constants to validate.
        rules: Validation rules to apply.

    Returns:
        ValidationResult with any errors found.
    """
    result = ValidationResult()

    # Build name → constant lookup
    by_name = {c.name: c for c in constants}

    for rule in rules:
        if rule.name not in by_name:
            # Constant not found — skip (it might be optional)
            logger.debug("Validator: constant '%s' not found in current set, skipping", rule.name)
            continue

        constant = by_name[rule.name]
        value = constant.value

        # Type check
        if rule.type:
            _check_type(constant, rule, result)

        # Range checks
        if rule.min is not None:
            if isinstance(value, (int, float)):
                if value < rule.min:
                    result.errors.append(ValidationError(
                        constant_name=rule.name,
                        rule="min",
                        message=f"{rule.name} = {value} is below minimum {rule.min}",
                    ))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    if isinstance(v, (int, float)) and v < rule.min:
                        result.errors.append(ValidationError(
                            constant_name=rule.name,
                            rule="min",
                            message=f"{rule.name}[{i}] = {v} is below minimum {rule.min}",
                        ))

        if rule.max is not None:
            if isinstance(value, (int, float)):
                if value > rule.max:
                    result.errors.append(ValidationError(
                        constant_name=rule.name,
                        rule="max",
                        message=f"{rule.name} = {value} exceeds maximum {rule.max}",
                    ))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    if isinstance(v, (int, float)) and v > rule.max:
                        result.errors.append(ValidationError(
                            constant_name=rule.name,
                            rule="max",
                            message=f"{rule.name}[{i}] = {v} exceeds maximum {rule.max}",
                        ))

        # Pattern check (string values)
        if rule.pattern:
            if isinstance(value, str):
                if not re.match(rule.pattern, value):
                    result.errors.append(ValidationError(
                        constant_name=rule.name,
                        rule="pattern",
                        message=f"{rule.name} = '{value}' does not match pattern '{rule.pattern}'",
                    ))

        # Length checks (arrays and strings)
        if rule.min_length is not None:
            length = len(value) if isinstance(value, (list, str)) else None
            if length is not None and length < rule.min_length:
                result.errors.append(ValidationError(
                    constant_name=rule.name,
                    rule="min_length",
                    message=f"{rule.name} has length {length}, minimum is {rule.min_length}",
                ))

        if rule.max_length is not None:
            length = len(value) if isinstance(value, (list, str)) else None
            if length is not None and length > rule.max_length:
                result.errors.append(ValidationError(
                    constant_name=rule.name,
                    rule="max_length",
                    message=f"{rule.name} has length {length}, maximum is {rule.max_length}",
                ))

        # Not-empty check
        if rule.not_empty:
            if value == "" or value == [] or value is None:
                result.errors.append(ValidationError(
                    constant_name=rule.name,
                    rule="not_empty",
                    message=f"{rule.name} must not be empty",
                ))

    return result


def _check_type(constant: Constant, rule: ValidationRule, result: ValidationResult):
    """Check if the constant's value matches the expected type."""
    value = constant.value
    expected = rule.type.lower() if rule.type else None

    if expected == "int":
        if not isinstance(value, int):
            result.errors.append(ValidationError(
                constant_name=rule.name,
                rule="type",
                message=f"{rule.name} = {value!r} is not an integer",
            ))
    elif expected == "float":
        if not isinstance(value, (int, float)):
            result.errors.append(ValidationError(
                constant_name=rule.name,
                rule="type",
                message=f"{rule.name} = {value!r} is not a float",
            ))
    elif expected == "string":
        if not isinstance(value, str):
            result.errors.append(ValidationError(
                constant_name=rule.name,
                rule="type",
                message=f"{rule.name} = {value!r} is not a string",
            ))
