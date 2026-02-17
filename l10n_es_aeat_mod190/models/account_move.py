# Copyright 2020 Creu Blanca
# Copyright 2024 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    aeat_perception_key_id = fields.Many2one(
        comodel_name="l10n.es.aeat.report.perception.key",
        string="Clave percepción",
        help="Se consignará la clave alfabética que corresponda a las "
        "percepciones de que se trate.",
    )
    aeat_perception_subkey_id = fields.Many2one(
        comodel_name="l10n.es.aeat.report.perception.subkey",
        string="Subclave",
        help="""Tratándose de percepciones correspondientes a las claves
                B, E, F, G, H, I, K y L, deberá consignarse, además, la
                subclave numérica de dos dígitos que corresponda a las
                percepciones de que se trate, según la relación de
                subclaves que para cada una de las mencionadas claves
                figura a continuación.
                En percepciones correspondientes a claves distintas de las
                mencionadas, no se cumplimentará este campo.
                Cuando deban consignarse en el modelo 190
                percepciones satisfechas a un mismo perceptor que
                correspondan a diferentes claves o subclaves de
                percepción, deberán cumplimentarle tantos apuntes o
                registros de percepción como sea necesario, de forma que
                cada uno de ellos refleje exclusivamente los datos de
                percepciones correspondientes a una misma clave y, en
                su caso, subclave.""",
    )

    def add_keys(self, set_fiscal_position=True):
        fiscal_position_model = self.env["account.fiscal.position"]
        for move in self:
            if not move.is_invoice(include_receipts=True):
                continue
            if set_fiscal_position:
                delivery_partner = move.partner_shipping_id or move.partner_id
                move.fiscal_position_id = fiscal_position_model.with_company(
                    move.company_id.id
                )._get_fiscal_position(move.partner_id, delivery=delivery_partner)
            if move.fiscal_position_id.aeat_perception_key_id:
                fp = move.fiscal_position_id
                move.aeat_perception_key_id = fp.aeat_perception_key_id
                move.aeat_perception_subkey_id = fp.aeat_perception_subkey_id

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        res = super()._onchange_partner_id()
        self.add_keys(set_fiscal_position=False)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered(lambda x: not x.fiscal_position_id).add_keys(set_fiscal_position=True)
        moves.filtered(lambda x: x.fiscal_position_id).add_keys(set_fiscal_position=False)
        return moves

    def write(self, vals):
        res = super().write(vals)
        if "fiscal_position_id" in vals:
            self.add_keys(set_fiscal_position=False)
        return res
