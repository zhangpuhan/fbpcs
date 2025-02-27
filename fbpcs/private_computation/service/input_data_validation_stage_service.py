#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict

import json
import logging
from typing import List, Optional

from fbpcp.service.onedocker import OneDockerService
from fbpcs.common.entity.stage_state_instance import StageStateInstance
from fbpcs.onedocker_binary_names import OneDockerBinaryNames
from fbpcs.private_computation.entity.pc_validator_config import (
    PCValidatorConfig,
)
from fbpcs.private_computation.entity.private_computation_instance import (
    PrivateComputationInstance,
    PrivateComputationRole,
)
from fbpcs.private_computation.entity.private_computation_status import (
    PrivateComputationInstanceStatus,
)
from fbpcs.private_computation.service.private_computation_stage_service import (
    PrivateComputationStageService,
)
from fbpcs.private_computation.service.utils import (
    get_pc_status_from_stage_state,
)

# 20 minutes
PRE_VALIDATION_CHECKS_TIMEOUT: int = 1200


class InputDataValidationStageService(PrivateComputationStageService):
    """
    This InputDataValidation stage service validates input data files.
    Validation fails if the issues detected in the data file
    do not pass the input_data_validation configuration minimum
    valid thresholds. A failing validation stage will prevent the next
    stage from running.

    It is implemented in a Cloud agnostic way.
    """

    def __init__(
        self, pc_validator_config: PCValidatorConfig, onedocker_svc: OneDockerService
    ) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._failed_status: PrivateComputationInstanceStatus = (
            PrivateComputationInstanceStatus.INPUT_DATA_VALIDATION_FAILED
        )
        self._pc_validator_config: PCValidatorConfig = pc_validator_config
        self._onedocker_svc = onedocker_svc

    async def run_async(
        self,
        pc_instance: PrivateComputationInstance,
        server_ips: Optional[List[str]] = None,
    ) -> PrivateComputationInstance:
        """
        Updates the status to COMPLETED and returns the pc_instance
        """
        self._logger.info("[PCPreValidation] - Starting stage")
        if self._should_run_pre_validation(pc_instance):
            self._logger.info(
                "[PCPreValidation] - starting a pc_pre_validation_cli run"
            )
            await self.run_pc_pre_validation_cli(pc_instance)
        else:
            self._logger.info("[PCPreValidation] - skipped run validations")

        self._logger.info("[PCPreValidation] - finished run_async")
        return pc_instance

    async def run_pc_pre_validation_cli(
        self, pc_instance: PrivateComputationInstance
    ) -> None:
        region = self._pc_validator_config.region
        cmd_args = [
            f"--input-file-path={pc_instance.input_path}",
            "--cloud-provider=AWS",
            f"--region={region}",
        ]
        threshold_overrides = (
            self._pc_validator_config.data_validation_threshold_overrides
        )
        if threshold_overrides:
            threshold_overrides_str = json.dumps(threshold_overrides)
            cmd_args.append(f"--valid-threshold-override='{threshold_overrides_str}'")

        cmd_args_str = " ".join(cmd_args)

        container_instance = self._onedocker_svc.start_container(
            package_name=OneDockerBinaryNames.PC_PRE_VALIDATION.value,
            timeout=PRE_VALIDATION_CHECKS_TIMEOUT,
            cmd_args=cmd_args_str,
        )
        stage_state = StageStateInstance(
            pc_instance.instance_id,
            pc_instance.current_stage.name,
            containers=[container_instance],
        )
        pc_instance.instances.append(stage_state)
        self._logger.info(
            f"[PCPreValidation] - Started container instance_id: {container_instance.instance_id} status: {container_instance.status}"
        )

    def get_status(
        self,
        pc_instance: PrivateComputationInstance,
    ) -> PrivateComputationInstanceStatus:
        """
        Returns the pc_instance's current status
        """
        # When this stage is enabled, it should return the status based on the container status
        if self._should_run_pre_validation(pc_instance):
            instance_status = get_pc_status_from_stage_state(
                pc_instance, self._onedocker_svc
            )

            task_id = ""
            if pc_instance.instances:
                last_instance = pc_instance.instances[-1]
                if isinstance(last_instance, StageStateInstance):
                    last_container = last_instance.containers[-1]
                    task_id = (
                        last_container.instance_id.split("/")[-1]
                        if last_container
                        else ""
                    )

            if instance_status == self._failed_status and task_id:
                region = self._pc_validator_config.region
                cluster = self._onedocker_svc.container_svc.get_cluster()
                failed_task_link = f"https://{region}.console.aws.amazon.com/ecs/home?region={region}#/clusters/{cluster}/tasks/{task_id}/details"

                error_message = (
                    f"[PCPreValidation] - stage failed because of some failed validations. Please check the logs in ECS for task id '{task_id}' to see the validation issues:\n"
                    + f"Failed task link: {failed_task_link}"
                )
                self._logger.error(error_message)
            elif instance_status == self._failed_status:
                self._logger.error(
                    "[PCPreValidation] - stage failed because of some failed validations. Please check the logs in ECS"
                )

            return instance_status

        return PrivateComputationInstanceStatus.INPUT_DATA_VALIDATION_COMPLETED

    def _should_run_pre_validation(
        self, pc_instance: PrivateComputationInstance
    ) -> bool:
        return (
            self._pc_validator_config.pc_pre_validator_enabled
            and pc_instance.role == PrivateComputationRole.PARTNER
        )
