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


def _get_csv_path():
    path = Path(__file__).parent / "mod190_partner_geo_fix_o18.csv"
    return path if path.exists() else None


def _apply_partner_geo_fix(env):
    csv_path = _get_csv_path()
    if not csv_path:
        _logger.warning("mod190 geo-fix CSV not found in migration folder")
        return

    cr = env.cr
    cr.execute("DROP TABLE IF EXISTS tmp_mod190_partner_geo_fix")
    cr.execute(
        """
        CREATE TEMP TABLE tmp_mod190_partner_geo_fix (
            vat varchar,
            country_code varchar,
            state_code varchar,
            key_code varchar,
            subkey_name varchar,
            incluir_190 varchar
        ) ON COMMIT DROP
        """
    )

    with csv_path.open("r", encoding="utf-8") as csv_file:
        cr.copy_expert(
            """
            COPY tmp_mod190_partner_geo_fix (
                vat, country_code, state_code, key_code, subkey_name, incluir_190
            )
            FROM STDIN WITH CSV HEADER
            """,
            csv_file,
        )

    cr.execute("SELECT count(*) FROM tmp_mod190_partner_geo_fix")
    loaded_rows = cr.fetchone()[0]

    cr.execute(
        """
        WITH src AS (
            SELECT
                regexp_replace(upper(COALESCE(vat, '')), '^ES', '') AS vat_norm,
                upper(NULLIF(country_code, '')) AS country_code,
                upper(NULLIF(state_code, '')) AS state_code,
                NULLIF(key_code, '') AS key_code,
                NULLIF(subkey_name, '') AS subkey_name,
                CASE
                    WHEN incluir_190 IN ('t', 'true', '1', 'T', 'TRUE') THEN TRUE
                    WHEN incluir_190 IN ('f', 'false', '0', 'F', 'FALSE') THEN FALSE
                    ELSE NULL
                END AS incluir_190
            FROM tmp_mod190_partner_geo_fix
        ),
        key_map AS (
            SELECT id, code
            FROM l10n_es_aeat_report_perception_key
            WHERE aeat_number = '190'
        ),
        subkey_map AS (
            SELECT
                sk.id,
                sk.name,
                sk.aeat_perception_key_id
            FROM l10n_es_aeat_report_perception_subkey sk
            WHERE sk.aeat_number = '190'
        ),
        data AS (
            SELECT
                src.vat_norm,
                rc.id AS country_id,
                rs.id AS state_id,
                km.id AS key_id,
                sm.id AS subkey_id,
                src.subkey_name,
                src.incluir_190
            FROM src
            LEFT JOIN res_country rc
                ON rc.code = src.country_code
            LEFT JOIN res_country_state rs
                ON rs.code = src.state_code
               AND (rc.id IS NULL OR rs.country_id = rc.id)
            LEFT JOIN key_map km
                ON km.code = src.key_code
            LEFT JOIN subkey_map sm
                ON sm.aeat_perception_key_id = km.id
               AND sm.name = src.subkey_name
        ),
        updated AS (
            UPDATE res_partner rp
            SET
                country_id = COALESCE(data.country_id, rp.country_id),
                state_id = COALESCE(data.state_id, rp.state_id),
                aeat_perception_key_id = COALESCE(data.key_id, rp.aeat_perception_key_id),
                aeat_perception_subkey_id = CASE
                    WHEN data.subkey_name IS NULL THEN rp.aeat_perception_subkey_id
                    ELSE COALESCE(data.subkey_id, rp.aeat_perception_subkey_id)
                END,
                incluir_190 = COALESCE(data.incluir_190, rp.incluir_190)
            FROM data
            WHERE regexp_replace(upper(COALESCE(rp.vat, '')), '^ES', '') = data.vat_norm
            RETURNING rp.id
        )
        SELECT count(*) FROM updated
        """
    )
    updated_rows = cr.fetchone()[0]

    cr.execute(
        """
        WITH src AS (
            SELECT
                regexp_replace(upper(COALESCE(vat, '')), '^ES', '') AS vat_norm
            FROM tmp_mod190_partner_geo_fix
        )
        SELECT count(*)
        FROM src
        WHERE NOT EXISTS (
            SELECT 1
            FROM res_partner rp
            WHERE regexp_replace(upper(COALESCE(rp.vat, '')), '^ES', '') = src.vat_norm
        )
        """
    )
    missing_partners = cr.fetchone()[0]

    _logger.info(
        "mod190 partner geo-fix migration: csv=%s loaded=%s updated=%s missing_partners=%s",
        csv_path,
        loaded_rows,
        updated_rows,
        missing_partners,
    )

    cr.execute("DROP TABLE IF EXISTS tmp_mod190_partner_geo_fix")


@openupgrade.migrate()
def migrate(env, version):
    _apply_partner_geo_fix(env)
