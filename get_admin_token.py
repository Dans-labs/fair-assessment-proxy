from tool_registry.config import load_service_config
import tool_registry.security as security

service_config = load_service_config()
ADMIN_TOKEN = security.generate_admin_token(service_config.admin_auth_key)
print(f"{ADMIN_TOKEN}") 
