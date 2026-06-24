import importlib.util
import sys
import types
from datetime import timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def load_scheduler_module(monkeypatch, config):
    class DummyScheduler:
        instances = []

        def __init__(self, **kwargs):
            self.job_kwargs = None
            self.__class__.instances.append(self)

        def add_job(self, func, **kwargs):
            self.job_kwargs = kwargs

        def start(self):
            pass

    class DummyCronTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    apscheduler_module = types.ModuleType("apscheduler")
    apscheduler_module.__path__ = []
    schedulers_module = types.ModuleType("apscheduler.schedulers")
    schedulers_module.__path__ = []
    triggers_module = types.ModuleType("apscheduler.triggers")
    triggers_module.__path__ = []
    blocking_module = types.ModuleType("apscheduler.schedulers.blocking")
    blocking_module.BlockingScheduler = DummyScheduler
    cron_module = types.ModuleType("apscheduler.triggers.cron")
    cron_module.CronTrigger = DummyCronTrigger

    utils_module = types.ModuleType("src.utils")
    utils_module.load_config = lambda: config
    utils_module.load_env = lambda: None
    utils_module.setup_logging = lambda unused_config: DummyLogger()
    utils_module.load_json = lambda path: None
    utils_module.pick_text = lambda unused_config, zh, en: en

    notifier_module = types.ModuleType("src.notifier")
    notifier_module.EmailNotifier = object
    dedupe_module = types.ModuleType("src.utils_1.push_dedupe")
    dedupe_module.mark_papers_as_pushed = lambda *args, **kwargs: 0
    main_module = types.ModuleType("main")
    main_module.main = lambda: None
    pytz_module = types.ModuleType("pytz")
    pytz_module.timezone = lambda name: timezone.utc

    fake_modules = {
        "apscheduler": apscheduler_module,
        "apscheduler.schedulers": schedulers_module,
        "apscheduler.schedulers.blocking": blocking_module,
        "apscheduler.triggers": triggers_module,
        "apscheduler.triggers.cron": cron_module,
        "src.utils": utils_module,
        "src.notifier": notifier_module,
        "src.utils_1.push_dedupe": dedupe_module,
        "main": main_module,
        "pytz": pytz_module,
    }
    for name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = f"scheduler_under_test_{id(config)}"
    spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / "scheduler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, DummyScheduler


def test_daily_job_uses_misfire_grace_time(monkeypatch):
    for configured_grace_time, expected_grace_time in [(None, 300), (900, 900)]:
        scheduler_config = {
            "enabled": True,
            "run_time": "09:00",
            "timezone": "Asia/Shanghai",
            "run_on_start": False,
            "notification": {"enabled": False},
        }
        if configured_grace_time is not None:
            scheduler_config["misfire_grace_time"] = configured_grace_time

        config = {"app": {"language": "en"}, "scheduler": scheduler_config}
        module, dummy_scheduler = load_scheduler_module(monkeypatch, config)

        module.main()

        assert (
            dummy_scheduler.instances[-1].job_kwargs["misfire_grace_time"]
            == expected_grace_time
        )
