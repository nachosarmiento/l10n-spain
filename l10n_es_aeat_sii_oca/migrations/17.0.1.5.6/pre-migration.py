# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET active = false
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = 'l10n_es_aeat_sii_oca'
           AND d.name IN ('invoice_sii_form', 'invoice_sii_form_connector')
           AND v.active IS DISTINCT FROM false
        """
    )
    cr.execute(
        """
        UPDATE ir_model_data
           SET noupdate = true
         WHERE model = 'ir.ui.view'
           AND module = 'l10n_es_aeat_sii_oca'
           AND name IN ('invoice_sii_form', 'invoice_sii_form_connector')
           AND noupdate IS DISTINCT FROM true
        """
    )
