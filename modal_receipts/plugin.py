"""Host-side phase bridge. Environments register by Harbor's trial context UUID."""

from harbor.models.job.plugin import BaseJobPlugin

from modal_receipts.manifest import write_job_manifest

ENVIRONMENTS = {}
ROLLOUT_TRIALS = set()


class RolloutEvidencePlugin(BaseJobPlugin):
    async def on_job_start(self, job):
        self._job_dir = job.job_dir
        job.on_trial_started(self.trial_start)
        job.on_agent_started(self.agent_start)
        job.on_agent_ended(self.agent_end)
        job.on_trial_ended(self.trial_end)
        job.on_trial_cancelled(self.trial_end)

    async def on_job_end(self, job_result):
        write_job_manifest(self._job_dir, job_result.trial_results)

    async def trial_start(self, event):
        ROLLOUT_TRIALS.add(str(event.trial_id))

    async def agent_start(self, event):
        environment = ENVIRONMENTS.get(str(event.trial_id))
        if environment is None:
            raise RuntimeError("RolloutEvidencePlugin requires GarnetModalEnvironment")
        await environment.begin_rollout_capture()

    async def agent_end(self, event):
        environment = ENVIRONMENTS.get(str(event.trial_id))
        if environment is None:
            raise RuntimeError(
                "Rollout evidence environment disappeared before AGENT_END"
            )
        await environment.freeze_rollout_capture()

    async def trial_end(self, event):
        ROLLOUT_TRIALS.discard(str(event.trial_id))
        ENVIRONMENTS.pop(str(event.trial_id), None)
