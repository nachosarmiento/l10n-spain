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
        store=True,
        compute="_compute_aeat_perception_key_id",
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
        store=True,
        compute="_compute_aeat_perception_subkey_id",
        domain="[('aeat_perception_key_id', '=', aeat_perception_key_id)]",
    )
    is_aeat_perception_subkey_visible = fields.Boolean(
        compute="_compute_is_aeat_perception_subkey_visible"
    )

    @api.depends("fiscal_position_id")
    def _compute_aeat_perception_key_id(self):
        for item in self.filtered(lambda x: x.fiscal_position_id):
            item.aeat_perception_key_id = item.fiscal_position_id.aeat_perception_key_id

    @api.depends("fiscal_position_id")
    def _compute_aeat_perception_subkey_id(self):
        for item in self.filtered(lambda x: x.fiscal_position_id):
            item.aeat_perception_subkey_id = (
                item.fiscal_position_id.aeat_perception_subkey_id
            )

    @api.depends("aeat_perception_key_id")
    def _compute_is_aeat_perception_subkey_visible(self):
        for record in self:
            record.is_aeat_perception_subkey_visible = bool(
                record.env["l10n.es.aeat.report.perception.subkey"].search(
                    [
                        (
                            "aeat_perception_key_id",
                            "=",
                            record.aeat_perception_key_id.id,
                        ),
                    ]
                )
            )

    def _assign_mod190_fiscal_position(self):
        fiscal_position_model = self.env["account.fiscal.position"]
        for move in self.filtered(
            lambda x: x.is_invoice(include_receipts=True)
            and x.partner_id
            and not x.fiscal_position_id
        ):
            delivery_partner = move.partner_shipping_id or move.partner_id
            move.fiscal_position_id = fiscal_position_model.with_company(
                move.company_id
            )._get_fiscal_position(move.partner_id, delivery=delivery_partner)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        res = super()._onchange_partner_id()
        self._assign_mod190_fiscal_position()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._assign_mod190_fiscal_position()
        return moves
