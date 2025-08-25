# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        DELETE FROM ir_ui_view
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE model = 'ir.ui.view'
               AND module = 'l10n_es_aeat_sii_oca'
               AND name IN ('invoice_sii_form', 'invoice_sii_form_connector')
         )
    """)
