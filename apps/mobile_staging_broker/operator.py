"""Narrow adapter over TASK-126 broker-only wrappers."""


class Task126Operator:
    def __init__(self, approval):
        self.approval = dict(approval)

    @staticmethod
    def _data_module():
        from tools import mobile_staging_data

        return mobile_staging_data

    def inspect(self, database_url, provider_subject):
        result = self._data_module().broker_fixture_lifecycle_inventory(
            self.approval, database_url, provider_subject
        )
        state = result.get("state")
        if state not in {"ready_basic", "ready_officer", "reset_required"}:
            raise RuntimeError("bounded operator state invalid")
        return state

    def mutate(self, operation, database_url, provider_subject):
        data = self._data_module()
        functions = {
            "grant": data.broker_grant_officer,
            "restore": data.broker_restore_basic,
            "reset": data.broker_reset_fixture_lifecycle,
        }
        function = functions.get(operation)
        if function is None:
            raise RuntimeError("bounded operator operation invalid")
        function(self.approval, database_url, provider_subject)
