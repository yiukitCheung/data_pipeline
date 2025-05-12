# config/config_loader.py
import yaml
import os

def load_setting(status = "development"):
    """
    Loads the Data Pipeline configuration from the data_pipeline_config.yaml file.
    
    Returns:
        dict: data_pipeline_config configuration dictionary.
    """
    
    config_path = os.path.join(os.path.dirname(__file__), "settings.yaml")
    
    try:
        
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)[status]
        return config
    
    except FileNotFoundError:
        print("Configuration file not found. Please ensure config/settings.yaml exists.")
        raise
    
    except yaml.YAMLError as e:
        print("Error reading the YAML configuration file.")
        raise e