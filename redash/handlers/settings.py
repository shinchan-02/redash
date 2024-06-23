import os
import logging
from logging.handlers import RotatingFileHandler
from flask import request
from redash.handlers.base import BaseResource
from redash.models import Organization, db
from redash.permissions import require_admin
from redash.settings.organization import settings as org_settings

LOG_DIR = '/app/logs'  # Example directory within the container
LOG_FILE = os.path.join(LOG_DIR, 'audit.log')
os.makedirs(LOG_DIR, exist_ok=True)


# Create a logger object
audit_logger = logging.getLogger('redash_audit')
audit_logger.setLevel(logging.INFO)

# Create a file handler
handler = RotatingFileHandler(LOG_FILE, maxBytes=10000000, backupCount=5)
handler.setLevel(logging.INFO)

# Create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handlers to the logger
audit_logger.addHandler(handler)

def get_settings_with_defaults(defaults, org):
    values = org.settings.get("settings", {})
    settings = {}

    for setting, default_value in defaults.items():
        current_value = values.get(setting)
        if current_value is None and default_value is None:
            continue

        if current_value is None:
            settings[setting] = default_value
        else:
            settings[setting] = current_value

    settings["auth_google_apps_domains"] = org.google_apps_domains

    return settings

class OrganizationSettings(BaseResource):
    @require_admin
    def get(self):
        settings = get_settings_with_defaults(org_settings, self.current_org)
        return {"settings": settings}

    @require_admin
    def post(self):
        new_values = request.json

        if self.current_org.settings.get("settings") is None:
            self.current_org.settings["settings"] = {}

        previous_values = {}
        for k, v in new_values.items():
            if k == "auth_google_apps_domains":
                previous_values[k] = self.current_org.google_apps_domains
                self.current_org.settings[Organization.SETTING_GOOGLE_APPS_DOMAINS] = v
            else:
                previous_values[k] = self.current_org.get_setting(k, raise_on_missing=False)
                self.current_org.set_setting(k, v)

        db.session.add(self.current_org)
        db.session.commit()

        # Log the settings change
        logger.info(f"User {self.current_user.id} updated settings for organization {self.current_org.id}: {new_values}")

        self.record_event(
            {
                "action": "edit",
                "object_id": self.current_org.id,
                "object_type": "settings",
                "new_values": new_values,
                "previous_values": previous_values,
            }
        )

        settings = get_settings_with_defaults(org_settings, self.current_org)
        return {"settings": settings}
