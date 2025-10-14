from openupgradelib import openupgrade


def _map_payload_type(cr):
    openupgrade.logged_query(
        cr,
        """
        UPDATE ai_bridge
        SET payload_type = 'record'
        WHERE payload_type = 'record_v0';
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _map_payload_type(env.cr)
