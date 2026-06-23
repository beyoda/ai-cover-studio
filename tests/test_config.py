from aivoice_studio.utils.config import ConfigLoader


def test_config_loads():
    config = ConfigLoader().load()
    assert config["app"]["name"] == "AI Cover Studio"
    assert "runtime" in config
