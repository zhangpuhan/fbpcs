#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict


"""
CLI for running validations on the input data for private computations


Usage:
    pc_pre_validation_cli
        --input-file-path=<input-file-path>
        --cloud-provider=<cloud-provider>
        --region=<region>
        [--access-key-id=<access-key-id>]
        [--access-key-data=<access-key-data>]
        [--start-timestamp=<start-timestamp>]
        [--end-timestamp=<end-timestamp>]
        [--valid-threshold-override=<valid-threshold-override>]
"""


from typing import cast

from docopt import docopt
from fbpcs.pc_pre_validation.binary_file_validator import BinaryFileValidator
from fbpcs.pc_pre_validation.enums import ValidationResult
from fbpcs.pc_pre_validation.input_data_validator import InputDataValidator
from fbpcs.pc_pre_validation.validator import Validator
from fbpcs.pc_pre_validation.validators_runner import run_validators
from fbpcs.private_computation.entity.cloud_provider import CloudProvider
from schema import Schema, Optional, Or, Use

INPUT_FILE_PATH = "--input-file-path"
CLOUD_PROVIDER = "--cloud-provider"
REGION = "--region"
ACCESS_KEY_ID = "--access-key-id"
ACCESS_KEY_DATA = "--access-key-data"
START_TIMESTAMP = "--start-timestamp"
END_TIMESTAMP = "--end-timestamp"
VALID_THRESHOLD_OVERRIDE = "--valid-threshold-override"


def main() -> None:
    optional_string = Or(None, str)
    cloud_provider_from_string = Use(lambda arg: CloudProvider[arg])

    s = Schema(
        {
            INPUT_FILE_PATH: str,
            CLOUD_PROVIDER: cloud_provider_from_string,
            REGION: str,
            Optional(ACCESS_KEY_ID): optional_string,
            Optional(ACCESS_KEY_DATA): optional_string,
            Optional(START_TIMESTAMP): optional_string,
            Optional(END_TIMESTAMP): optional_string,
            Optional(VALID_THRESHOLD_OVERRIDE): optional_string,
        }
    )
    arguments = s.validate(docopt(__doc__))
    assert arguments
    print("Parsed pc_pre_validation_cli arguments")

    validators = [
        cast(
            Validator,
            InputDataValidator(
                arguments[INPUT_FILE_PATH],
                arguments[CLOUD_PROVIDER],
                arguments[REGION],
                arguments[ACCESS_KEY_ID],
                arguments[ACCESS_KEY_DATA],
            ),
        ),
        cast(
            Validator,
            BinaryFileValidator(
                region=arguments[REGION],
                access_key_id=arguments[ACCESS_KEY_ID],
                access_key_data=arguments[ACCESS_KEY_DATA],
            ),
        ),
    ]

    (aggregated_result, aggregated_report) = run_validators(validators)

    if aggregated_result == ValidationResult.FAILED:
        raise Exception(aggregated_report)
    elif aggregated_result == ValidationResult.SUCCESS:
        print(f"Success: {aggregated_report}")
    else:
        raise Exception(
            "Unknown validation result: {aggregated_result}.\n"
            + "Validation report: {aggregated_report}"
        )


if __name__ == "__main__":
    main()
