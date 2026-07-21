from fair_assessment_proxy.config import load_service_config
import fair_assessment_proxy.security as security

service_config = load_service_config()
ADMIN_TOKEN = security.generate_admin_token(service_config.admin_auth_key)
print(f"{ADMIN_TOKEN}")
