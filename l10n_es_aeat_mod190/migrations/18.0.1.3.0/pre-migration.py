import logging
from pathlib import Path

try:
    from openupgradelib import openupgrade
except ImportError:  # pragma: no cover
    class _OpenUpgradeFallback:
        @staticmethod
        def migrate(*args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

    openupgrade = _OpenUpgradeFallback()

_logger = logging.getLogger(__name__)


def _migrate_partner_subkeys_from_csv(env):
    csv_path = Path(__file__).parent / "mod190_partner_subkeys_o16.csv"
    if not csv_path.exists():
        _logger.warning("mod190 subkeys CSV not found: %s", csv_path)
        return

    cr = env.cr
    cr.execute("DROP TABLE IF EXISTS tmp_mod190_partner_subkeys")
    cr.execute(
        """
        CREATE TEMP TABLE tmp_mod190_partner_subkeys (
            partner_id integer,
            vat varchar,
            partner_name varchar,
            key_code varchar,
            subkey_name varchar
        ) ON COMMIT DROP
        """
    )
    with csv_path.open("r", encoding="utf-8") as csv_file:
        cr.copy_expert(
            """
            COPY tmp_mod190_partner_subkeys (
                partner_id, vat, partner_name, key_code, subkey_name
            )
            FROM STDIN WITH CSV HEADER
            """,
            csv_file,
        )

    cr.execute("SELECT count(*) FROM tmp_mod190_partner_subkeys")
    loaded_rows = cr.fetchone()[0]

    cr.execute(
        """
        WITH key_subkey AS (
            SELECT
                k.id AS key_id,
                k.code AS key_code,
                sk.id AS subkey_id,
                sk.name AS subkey_name
            FROM l10n_es_aeat_report_perception_key k
            JOIN l10n_es_aeat_report_perception_subkey sk
                ON sk.aeat_perception_key_id = k.id
            WHERE k.aeat_number = '190'
              AND sk.aeat_number = '190'
        )
        UPDATE res_partner rp
        SET aeat_perception_subkey_id = ks.subkey_id
        FROM tmp_mod190_partner_subkeys t
        JOIN key_subkey ks
            ON ks.key_code = t.key_code
           AND ks.subkey_name = t.subkey_name
        WHERE rp.id = t.partner_id
          AND rp.aeat_perception_key_id = ks.key_id
          AND rp.aeat_perception_subkey_id IS DISTINCT FROM ks.subkey_id
        """
    )
    updated_by_id = cr.rowcount

    cr.execute(
        """
        WITH key_subkey AS (
            SELECT
                k.id AS key_id,
                k.code AS key_code,
                sk.id AS subkey_id,
                sk.name AS subkey_name
            FROM l10n_es_aeat_report_perception_key k
            JOIN l10n_es_aeat_report_perception_subkey sk
                ON sk.aeat_perception_key_id = k.id
            WHERE k.aeat_number = '190'
              AND sk.aeat_number = '190'
        ),
        src AS (
            SELECT DISTINCT
                regexp_replace(upper(COALESCE(vat, '')), '^ES', '') AS vat_norm,
                key_code,
                subkey_name
            FROM tmp_mod190_partner_subkeys
            WHERE COALESCE(vat, '') <> ''
        )
        UPDATE res_partner rp
        SET aeat_perception_subkey_id = ks.subkey_id
        FROM src
        JOIN key_subkey ks
            ON ks.key_code = src.key_code
           AND ks.subkey_name = src.subkey_name
        WHERE regexp_replace(upper(COALESCE(rp.vat, '')), '^ES', '') = src.vat_norm
          AND rp.aeat_perception_key_id = ks.key_id
          AND rp.aeat_perception_subkey_id IS NULL
        """
    )
    updated_by_vat = cr.rowcount

    _logger.info(
        "mod190 partner subkeys migration: loaded=%s updated_by_id=%s updated_by_vat=%s",
        loaded_rows,
        updated_by_id,
        updated_by_vat,
    )
    cr.execute("DROP TABLE IF EXISTS tmp_mod190_partner_subkeys")


@openupgrade.migrate()
def migrate(env, version):
    _migrate_partner_subkeys_from_csv(env)
