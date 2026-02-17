import logging

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


_PARTNER_HITS_CTE = """
WITH map_lines AS (
    SELECT
        ml.id AS map_line_id,
        ml.field_number,
        ml.field_type,
        tt.name AS tax_template_name
    FROM l10n_es_aeat_map_tax mt
    JOIN l10n_es_aeat_map_tax_line ml
        ON ml.map_parent_id = mt.id
    JOIN l10n_es_aeat_map_tax_line_l10n_es_aeat_map_tax_line_tax_rel rel
        ON rel.l10n_es_aeat_map_tax_line_id = ml.id
    JOIN l10n_es_aeat_map_tax_line_tax tt
        ON tt.id = rel.l10n_es_aeat_map_tax_line_tax_id
    WHERE mt.model::varchar = '190'
      AND ml.field_number IN (11, 12, 13, 14, 15, 16)
),
company_taxes AS (
    SELECT
        c.id AS company_id,
        ml.field_number,
        ml.field_type,
        imd.res_id AS tax_id
    FROM res_company c
    JOIN map_lines ml ON TRUE
    JOIN ir_model_data imd
        ON imd.model = 'account.tax'
       AND imd.module = 'account'
       AND imd.name = c.id::varchar || '_' || ml.tax_template_name
),
partner_hits AS (
    SELECT
        aml.partner_id,
        bool_or(ct.field_number IN (11, 12, 13, 14)) AS has_work_fields,
        bool_or(ct.field_number IN (15, 16)) AS has_economic_fields
    FROM account_move_line aml
    JOIN account_move am
        ON am.id = aml.move_id
    JOIN company_taxes ct
        ON ct.company_id = aml.company_id
    WHERE am.state = 'posted'
      AND aml.partner_id IS NOT NULL
      AND (
        (ct.field_type = 'base' AND EXISTS (
            SELECT 1
            FROM account_move_line_account_tax_rel atr
            WHERE atr.account_move_line_id = aml.id
              AND atr.account_tax_id = ct.tax_id
        ))
        OR (ct.field_type = 'amount' AND aml.tax_line_id = ct.tax_id)
        OR (ct.field_type = 'both' AND (
            aml.tax_line_id = ct.tax_id
            OR EXISTS (
                SELECT 1
                FROM account_move_line_account_tax_rel atr2
                WHERE atr2.account_move_line_id = aml.id
                  AND atr2.account_tax_id = ct.tax_id
            )
        ))
      )
    GROUP BY aml.partner_id
)
"""


def _auto_assign_g01_for_economic_only(env):
    cr = env.cr
    cr.execute(
        _PARTNER_HITS_CTE
        + """
        , g_key AS (
            SELECT id
            FROM l10n_es_aeat_report_perception_key
            WHERE aeat_number = '190'
              AND code = 'G'
            LIMIT 1
        ),
        g_subkey AS (
            SELECT sk.id
            FROM l10n_es_aeat_report_perception_subkey sk
            JOIN g_key gk
                ON gk.id = sk.aeat_perception_key_id
            WHERE sk.aeat_number = '190'
              AND sk.name = '01'
            LIMIT 1
        ),
        updated AS (
            UPDATE res_partner rp
            SET
                aeat_perception_key_id = gk.id,
                aeat_perception_subkey_id = gs.id
            FROM partner_hits ph
            CROSS JOIN g_key gk
            CROSS JOIN g_subkey gs
            WHERE rp.id = ph.partner_id
              AND ph.has_economic_fields
              AND NOT ph.has_work_fields
              AND rp.aeat_perception_key_id IS NULL
            RETURNING rp.id
        )
        SELECT count(*) FROM updated
        """
    )
    updated = cr.fetchone()[0]
    _logger.info(
        "mod190 auto-fix: partners with economic-only activity set to G/01 = %s",
        updated,
    )


def _log_mod190_pending_partners(env):
    cr = env.cr
    cr.execute(
        _PARTNER_HITS_CTE
        + """
        SELECT
            rp.id,
            rp.name,
            COALESCE(rp.vat, '') AS vat,
            COALESCE(k.code, '') AS key_code,
            COALESCE(sk.name, '') AS subkey_name,
            ph.has_work_fields,
            ph.has_economic_fields,
            (COALESCE(rp.vat, '') = '' OR rp.state_id IS NULL) AS missing_partner_data
        FROM partner_hits ph
        JOIN res_partner rp
            ON rp.id = ph.partner_id
        LEFT JOIN l10n_es_aeat_report_perception_key k
            ON k.id = rp.aeat_perception_key_id
        LEFT JOIN l10n_es_aeat_report_perception_subkey sk
            ON sk.id = rp.aeat_perception_subkey_id
        WHERE k.id IS NULL
           OR (k.code IN ('B', 'E', 'F', 'G', 'H', 'I', 'L') AND sk.id IS NULL)
        ORDER BY rp.name
        """
    )
    rows = cr.fetchall()
    if not rows:
        _logger.info("mod190 pending review after auto-fix: none")
        return

    _logger.warning("mod190 pending review after auto-fix: %s partner(s)", len(rows))
    for (
        partner_id,
        name,
        vat,
        key_code,
        subkey_name,
        has_work_fields,
        has_economic_fields,
        missing_partner_data,
    ) in rows:
        _logger.warning(
            "mod190 pending partner id=%s name=%s vat=%s key=%s subkey=%s "
            "has_work=%s has_economic=%s missing_vat_or_state=%s",
            partner_id,
            name,
            vat,
            key_code,
            subkey_name,
            has_work_fields,
            has_economic_fields,
            missing_partner_data,
        )


@openupgrade.migrate()
def migrate(env, version):
    _auto_assign_g01_for_economic_only(env)
    _log_mod190_pending_partners(env)
