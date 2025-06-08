import datetime
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    cron = env.ref(
        "ai_bridge_discuss_agent_base.ir_cron_update_agent_users_online_status"
    )
    if cron:
        cron.write(
            {
                "nextcall": (
                    datetime.datetime.now() + datetime.timedelta(minutes=5)
                ).strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    else:
        _logger.error("Cron job ir_cron_update_user_online not found")
