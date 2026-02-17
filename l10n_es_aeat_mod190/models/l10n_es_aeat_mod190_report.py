# Copyright 2019 Creu Blanca
# Copyright 2024 Tecnativa - Victor Martinez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, exceptions, fields, models
from odoo.tools import float_compare

from odoo.addons.l10n_es_aeat.models.spanish_states_mapping import SPANISH_STATES


class L10nEsAeatMod190Report(models.Model):
    _description = "AEAT 190 report"
    _inherit = "l10n.es.aeat.report.tax.mapping"
    _name = "l10n.es.aeat.mod190.report"
    _aeat_number = "190"
    _period_quarterly = False
    _period_monthly = False
    _period_yearly = True

    casilla_01 = fields.Integer(string="[01] Recipients", readonly=True)
    casilla_02 = fields.Float(string="[02] Amount of perceptions")
    casilla_03 = fields.Float(string="[03] Amount of retentions")
    partner_record_ids = fields.One2many(
        comodel_name="l10n.es.aeat.mod190.report.line",
        inverse_name="report_id",
        string="Partner records",
    )
    registro_manual = fields.Boolean(string="Manual records", default=False)
    calculado = fields.Boolean(string="Calculated", default=False)

    def _check_report_lines(self):
        """Checks if all report line fields are filled."""
        for report in self:
            for partner_record in report.partner_record_ids:
                if not partner_record.partner_record_ok:
                    raise exceptions.UserError(
                        _(
                            "All partner records fields (country, VAT number) "
                            "must be filled."
                        )
                    )

    def button_confirm(self):
        for report in self:
            valid = report.casilla_01 == len(report.partner_record_ids)

            percepciones = 0.0
            retenciones = 0.0
            for line in report.partner_record_ids:
                percepciones += (
                    line.percepciones_dinerarias
                    + line.percepciones_en_especie
                    + line.percepciones_dinerarias_incap
                    + line.percepciones_en_especie_incap
                )
                retenciones += (
                    line.retenciones_dinerarias + line.retenciones_dinerarias_incap
                )

            if float_compare(report.casilla_02, percepciones, precision_digits=2) != 0:
                valid = False
            if float_compare(report.casilla_03, retenciones, precision_digits=2) != 0:
                valid = False

            if not valid:
                raise exceptions.UserError(
                    _("You have to recalculate the report before confirm it.")
                )

        self._check_report_lines()
        return super().button_confirm()

    # flake8: noqa: C901
    def calculate(self):
        res = super().calculate()
        line_model = self.env["l10n.es.aeat.mod190.report.line"]
        for report in self:
            if not report.registro_manual:
                report.partner_record_ids.unlink()

            tax_lines = report.tax_line_ids.filtered(
                lambda x: x.field_number in (11, 12, 13, 14, 15, 16)
                and x.res_id == report.id
            )
            tax_line_vals = {}

            for tax_line in tax_lines:
                for move_line in tax_line.move_line_ids:
                    partner = move_line.partner_id
                    key_id = move_line.aeat_perception_key_id or partner.aeat_perception_key_id
                    subkey_id = (
                        move_line.aeat_perception_subkey_id
                        or partner.aeat_perception_subkey_id
                    )

                    if not key_id:
                        raise exceptions.UserError(
                            _(
                                "The perception key of the partner, %(partner)s. "
                                "Must be filled."
                            )
                            % {"partner": partner.name}
                        )

                    tax_line_vals.setdefault(partner.id, {})
                    tax_line_vals[partner.id].setdefault(key_id.id, {})

                    subkey_key = subkey_id.id if subkey_id else False
                    if subkey_key not in tax_line_vals[partner.id][key_id.id]:
                        tax_line_vals[partner.id][key_id.id][subkey_key] = {}
                        partner_record_exists = report.partner_record_ids.filtered(
                            lambda r, p=partner, k=key_id, s=subkey_id: r.partner_id == p
                            and r.aeat_perception_key_id == k
                            and r.aeat_perception_subkey_id == s
                        )
                        if partner_record_exists:
                            tax_line_vals[partner.id][key_id.id][subkey_key] = False
                        else:
                            tax_line_vals[partner.id][key_id.id][
                                subkey_key
                            ] = report._get_line_mod190_vals(partner, key_id, subkey_id)

                    if report.registro_manual:
                        continue

                    values = tax_line_vals[partner.id][key_id.id][subkey_key]
                    if not values:
                        continue

                    percepciones_dinerarias = 0.0
                    retenciones_dinerarias = 0.0
                    percepciones_especie = 0.0
                    ingresos_repercutidos = 0.0

                    if tax_line.field_number in (11, 15) and tax_line.res_id == report.id:
                        percepciones_dinerarias += move_line.debit - move_line.credit
                    if tax_line.field_number in (12, 16) and tax_line.res_id == report.id:
                        retenciones_dinerarias += move_line.credit - move_line.debit
                    if tax_line.field_number == 13 and tax_line.res_id == report.id:
                        percepciones_especie += move_line.debit - move_line.credit
                        ingresos_repercutidos += move_line.credit - move_line.debit

                    if not partner.discapacidad or partner.discapacidad == "0":
                        values["percepciones_dinerarias"] += percepciones_dinerarias
                        values["retenciones_dinerarias"] += retenciones_dinerarias
                        values["percepciones_en_especie"] += (
                            percepciones_especie - ingresos_repercutidos
                        )
                        values["ingresos_a_cuenta_efectuados"] += percepciones_especie
                        values["ingresos_a_cuenta_repercutidos"] += ingresos_repercutidos
                    else:
                        values["percepciones_dinerarias_incap"] += percepciones_dinerarias
                        values["retenciones_dinerarias_incap"] += retenciones_dinerarias
                        values["percepciones_en_especie_incap"] += (
                            percepciones_especie - ingresos_repercutidos
                        )
                        values["ingresos_a_cuenta_efectuados_incap"] += percepciones_especie
                        values["ingresos_a_cuenta_repercutidos_incap"] += ingresos_repercutidos

            registros = 0
            for partner_vals in tax_line_vals.values():
                for key_vals in partner_vals.values():
                    for values in key_vals.values():
                        registros += 1
                        if values:
                            line_model.create(values)

            report._calculate_amount(registros)
            report.calculado = True

        return res

    def _calculate_amount(self, registros):
        self.ensure_one()
        percepciones = 0.0
        retenciones = 0.0

        if self.registro_manual:
            registros = 0
            for line in self.partner_record_ids:
                registros += 1
                percepciones += (
                    line.percepciones_dinerarias
                    + line.percepciones_en_especie
                    + line.percepciones_dinerarias_incap
                    + line.percepciones_en_especie_incap
                )
                retenciones += (
                    line.retenciones_dinerarias + line.retenciones_dinerarias_incap
                )
        else:
            percepciones_lines = self.tax_line_ids.filtered(
                lambda x: x.field_number in (11, 13, 15)
                and x.model == "l10n.es.aeat.mod190.report"
                and x.res_id == self.id
            )
            for tax_line in percepciones_lines:
                for move_line in tax_line.move_line_ids:
                    percepciones += move_line.debit - move_line.credit

            retenciones_lines = self.tax_line_ids.filtered(
                lambda x: x.field_number in (12, 14, 16)
                and x.model == "l10n.es.aeat.mod190.report"
                and x.res_id == self.id
            )
            for tax_line in retenciones_lines:
                for move_line in tax_line.move_line_ids:
                    retenciones += move_line.credit - move_line.debit

        self.casilla_01 = registros
        self.casilla_02 = percepciones
        self.casilla_03 = retenciones

    def _get_line_mod190_vals(self, partner, key_id, subkey_id):
        state_code = SPANISH_STATES.get(partner.state_id.code)
        if not state_code:
            exceptions.UserError(
                _("The state is not defined in the partner, %s") % partner.name
            )

        vals = {
            "report_id": self.id,
            "partner_id": partner.id,
            "partner_vat": partner.vat,
            "aeat_perception_key_id": key_id.id,
            "aeat_perception_subkey_id": subkey_id.id if subkey_id else False,
            "codigo_provincia": state_code,
            "ceuta_melilla": partner.ceuta_melilla,
            "partner_record_ok": True,
            "percepciones_dinerarias": 0,
            "retenciones_dinerarias": 0,
            "percepciones_en_especie": 0,
            "ingresos_a_cuenta_efectuados": 0,
            "ingresos_a_cuenta_repercutidos": 0,
            "percepciones_dinerarias_incap": 0,
            "retenciones_dinerarias_incap": 0,
            "percepciones_en_especie_incap": 0,
            "ingresos_a_cuenta_efectuados_incap": 0,
            "ingresos_a_cuenta_repercutidos_incap": 0,
        }

        if key_id.ad_required + (subkey_id.ad_required if subkey_id else 0) >= 2:
            vals.update(
                {
                    "a_nacimiento": partner.a_nacimiento,
                    "discapacidad": partner.discapacidad,
                    "movilidad_geografica": partner.movilidad_geografica,
                    "representante_legal_vat": partner.representante_legal_vat,
                    "situacion_familiar": partner.situacion_familiar,
                    "nif_conyuge": partner.nif_conyuge,
                    "contrato_o_relacion": partner.contrato_o_relacion,
                    "hijos_y_descendientes_m": partner.hijos_y_descendientes_m,
                    "hijos_y_descendientes_m_entero": partner.hijos_y_descendientes_m_entero,
                    "hijos_y_descendientes": partner.hijos_y_descendientes_m,
                    "hijos_y_descendientes_entero": partner.hijos_y_descendientes_entero,
                    "computo_primeros_hijos_1": partner.computo_primeros_hijos_1,
                    "computo_primeros_hijos_2": partner.computo_primeros_hijos_2,
                    "computo_primeros_hijos_3": partner.computo_primeros_hijos_3,
                    "hijos_y_desc_discapacidad_33": partner.hijos_y_desc_discapacidad_33,
                    "hijos_y_desc_discapacidad_entero_33": partner.hijos_y_desc_discapacidad_entero_33,
                    "hijos_y_desc_discapacidad_mr": partner.hijos_y_desc_discapacidad_mr,
                    "hijos_y_desc_discapacidad_entero_mr": partner.hijos_y_desc_discapacidad_entero_mr,
                    "hijos_y_desc_discapacidad_66": partner.hijos_y_desc_discapacidad_66,
                    "hijos_y_desc_discapacidad_entero_66": partner.hijos_y_desc_discapacidad_entero_66,
                    "ascendientes": partner.ascendientes,
                    "ascendientes_entero": partner.ascendientes_entero,
                    "ascendientes_m75": partner.ascendientes_m75,
                    "ascendientes_entero_m75": partner.ascendientes_entero_m75,
                    "ascendientes_discapacidad_33": partner.ascendientes_discapacidad_33,
                    "ascendientes_discapacidad_entero_33": partner.ascendientes_discapacidad_entero_33,
                    "ascendientes_discapacidad_mr": partner.ascendientes_discapacidad_mr,
                    "ascendientes_discapacidad_entero_mr": partner.ascendientes_discapacidad_entero_mr,
                    "ascendientes_discapacidad_66": partner.ascendientes_discapacidad_66,
                    "ascendientes_discapacidad_entero_66": partner.ascendientes_discapacidad_entero_66,
                }
            )

        return vals


class L10nEsAeatMod190ReportLine(models.Model):
    _name = "l10n.es.aeat.mod190.report.line"
    _description = "Line for AEAT report Mod 190"

    @api.depends(
        "partner_vat",
        "a_nacimiento",
        "codigo_provincia",
        "aeat_perception_key_id",
        "partner_id",
    )
    def _compute_partner_record_ok(self):
        """Checks if all required fields are filled in report lines."""
        for record in self:
            record.partner_record_ok = bool(
                record.partner_vat
                and record.codigo_provincia
                and record.aeat_perception_key_id
                and record
            )

    report_id = fields.Many2one(
        comodel_name="l10n.es.aeat.mod190.report",
        string="AEAT 190 Report ID",
        ondelete="cascade",
    )
    state = fields.Selection(related="report_id.state")
    partner_record_ok = fields.Boolean(
        compute="_compute_partner_record_ok",
        store=True,
        string="Partner Record OK",
        help="Checked if partner record is OK",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner", string="Partner", required=True
    )
    partner_vat = fields.Char(string="NIF")
    representante_legal_vat = fields.Char(string="L. R. VAT")
    aeat_perception_key_id = fields.Many2one(
        comodel_name="l10n.es.aeat.report.perception.key",
        string="Perception key",
        required=True,
    )
    aeat_perception_subkey_id = fields.Many2one(
        comodel_name="l10n.es.aeat.report.perception.subkey",
        string="Perception subkey",
    )
    ejercicio_devengo = fields.Char(string="year")
    ceuta_melilla = fields.Char(string="Ceuta or Melilla")

    percepciones_dinerarias = fields.Float(string="Monetary perceptions")
    retenciones_dinerarias = fields.Float(string="Money withholdings")
    percepciones_en_especie = fields.Float(string="Valuation")
    ingresos_a_cuenta_efectuados = fields.Float(string="Income paid on account")
    ingresos_a_cuenta_repercutidos = fields.Float(string="Income paid into account")
    percepciones_dinerarias_incap = fields.Float(
        string="Monetary perceptions derived from incapacity for work"
    )
    retenciones_dinerarias_incap = fields.Float(
        string="Monetary withholdings derived from incapacity for work"
    )
    percepciones_en_especie_incap = fields.Float(
        string="Perceptions in kind arising from incapacity for work"
    )
    ingresos_a_cuenta_efectuados_incap = fields.Float(
        string="Income on account in kind made as a result of incapacity for work"
    )
    ingresos_a_cuenta_repercutidos_incap = fields.Float(
        string="Income to account in kind, repercussions derived from incapacity for work"
    )
    codigo_provincia = fields.Char(string="State ISO code")

    a_nacimiento = fields.Char(string="Year of birth")
    situacion_familiar = fields.Selection(
        selection=[
            (
                "1",
                "1 - Single, widowed, divorced or separated with children "
                "under 18 or incapacitated",
            ),
            (
                "2",
                "2 - Married and not legally separated and your spouse has "
                "no annual income above the amount referred to",
            ),
            ("3", "3 - Other."),
        ],
        string="Family situation",
    )
    nif_conyuge = fields.Char(string="VAT of the spouse")
    discapacidad = fields.Selection(
        selection=[
            ("0", "0 - No disability or degree of disability less than 33 percent."),
            (
                "1",
                "1 - Degree of disability greater than 33 percent and less than "
                "66 percent.",
            ),
            (
                "2",
                "2 - Degree of disability greater than 33 percent and less than "
                "66 percent, and reduced mobility.",
            ),
            ("3", "3 - Degree of disability equal to or greater than 65%."),
        ],
        string="Disability",
    )
    contrato_o_relacion = fields.Selection(
        selection=[
            ("1", "1 - Contract or relationship of a general nature"),
            ("2", "2 - Contract or ratio less than a year"),
            (
                "3",
                "3 - Contract or special employment relationship of a dependent nature",
            ),
            ("4", "4 - Sporadic relationship of manual workers"),
        ],
        string="Contract or relationship",
    )
    movilidad_geografica = fields.Selection(
        selection=[("0", "NO"), ("1", "SI")],
        string="Geographical mobility",
    )
    reduccion_aplicable = fields.Float(string="Applicable reduction")
    gastos_deducibles = fields.Float(string="Deductible expenses")
    pensiones_compensatorias = fields.Float(string="Compensatory pensions")
    anualidades_por_alimentos = fields.Float(string="Annuities for food")
    prestamos_vh = fields.Selection(
        selection=[
            (
                "0",
                "0 - Si en ningun momento del ejercicio ha resultado de "
                "aplicacion la reduccion del tipo de retencion.",
            ),
            (
                "1",
                "1 - Si en algun momento del ejercicio ha resultado de "
                "aplicacion la reduccion del tipo de retencion.",
            ),
        ],
        string="Comunicacion prestamos vivienda habitual",
    )

    hijos_y_descendientes_m = fields.Integer(string="Under 3 years")
    hijos_y_descendientes_m_entero = fields.Integer(
        string="Under 3 years, computed entirely"
    )
    hijos_y_descendientes = fields.Integer(string="Rest")
    hijos_y_descendientes_entero = fields.Integer(string="Rest, computed entirely")

    hijos_y_desc_discapacidad_mr = fields.Integer(
        string="Descendientes con discapacidad"
    )
    hijos_y_desc_discapacidad_entero_mr = fields.Integer(
        string="Descendientes con discapacidad, computado de forma entera"
    )
    hijos_y_desc_discapacidad_33 = fields.Integer(
        string="Hijos y descendientes con discapacidad del 33%"
    )
    hijos_y_desc_discapacidad_entero_33 = fields.Integer(
        string="Hijos y descendientes con discapacidad del 33%, computados por entero"
    )
    hijos_y_desc_discapacidad_66 = fields.Integer(
        string="Hijos y descendientes con discapacidad del 66%"
    )
    hijos_y_desc_discapacidad_entero_66 = fields.Integer(
        string="Hijos y descendientes con discapacidad del 66%, computados por entero"
    )
    ascendientes = fields.Integer(string="Ascendientes menores de 75 anos")
    ascendientes_entero = fields.Integer(
        string="Ascendientes menores de 75 anos, computados por entero"
    )
    ascendientes_m75 = fields.Integer(string="Ascendientes mayores de 75 anos")
    ascendientes_entero_m75 = fields.Integer(
        string="Ascendientes mayores de 75 anos, computados por entero"
    )

    ascendientes_discapacidad_33 = fields.Integer(
        string="Ascendientes con discapacidad"
    )
    ascendientes_discapacidad_entero_33 = fields.Integer(
        string="Ascendientes con discapacidad, computados por entero"
    )
    ascendientes_discapacidad_mr = fields.Integer(
        string="Ascendientes con discapacidad de mas del 33%"
    )
    ascendientes_discapacidad_entero_mr = fields.Integer(
        string="Ascendientes con discapacidad de mas del 33%, computados por entero"
    )
    ascendientes_discapacidad_66 = fields.Integer(
        string="Ascendientes con discapacidad de mas del 66%"
    )
    ascendientes_discapacidad_entero_66 = fields.Integer(
        string="Ascendientes con discapacidad de mas del 66%, computados por entero"
    )
    computo_primeros_hijos_1 = fields.Integer(string="1")
    computo_primeros_hijos_2 = fields.Integer(string="2")
    computo_primeros_hijos_3 = fields.Integer(string="3")

    ad_required = fields.Integer(compute="_compute_ad_required")

    # Keep 18.0 extra fields to avoid breaking 2025 export definitions.
    rendimientos_obtenidos_fondos = fields.Boolean(
        string="Rendimientos del trabajo obtenidos por la gestion de fondos"
    )
    clave_b01_jubilacion = fields.Boolean(string="Prestacion de jubilacion")
    clave_b01_viudedad = fields.Boolean(string="Prestacion de viudedad")
    clave_b01_incapacidad = fields.Boolean(
        string="Prestacion de incapacidad permanente total o parcial"
    )
    clave_b01_pensiones_no_contributivas = fields.Boolean(
        string="Prestacion de pensiones no contributivas por invalidez o jubilacion"
    )
    clave_b01_resto = fields.Boolean(string="Prestacion no incluida en el resto")
    visible_key_b01 = fields.Boolean(compute="_compute_visible_key_b01")

    @api.depends("aeat_perception_key_id", "aeat_perception_subkey_id")
    def _compute_ad_required(self):
        for record in self:
            ad_required = record.aeat_perception_key_id.ad_required
            if record.aeat_perception_subkey_id:
                ad_required += record.aeat_perception_subkey_id.ad_required
            record.ad_required = ad_required

    @api.depends("aeat_perception_key_id", "aeat_perception_subkey_id")
    def _compute_visible_key_b01(self):
        key_b = self.env.ref("l10n_es_aeat_mod190.aeat_m190_perception_key_02")
        subkey_b01 = self.env.ref(
            "l10n_es_aeat_mod190.aeat_m190_perception_subkey_02_01"
        )
        for record in self:
            record.visible_key_b01 = (
                record.aeat_perception_key_id == key_b
                and record.aeat_perception_subkey_id == subkey_b01
            )

    @api.onchange("partner_id")
    def onchange_partner_id(self):
        if self.partner_id:
            partner = self.partner_id
            if not partner.state_id:
                raise exceptions.UserError(_("Provincia no definida en el cliente"))

            self.codigo_provincia = SPANISH_STATES.get(partner.state_id.code)
            if not self.codigo_provincia:
                self.codigo_provincia = "98"

            self.partner_vat = partner.vat
            self.aeat_perception_key_id = partner.aeat_perception_key_id
            self.aeat_perception_subkey_id = partner.aeat_perception_subkey_id
            self.a_nacimiento = partner.a_nacimiento
            self.discapacidad = partner.discapacidad
            self.ceuta_melilla = partner.ceuta_melilla
            self.movilidad_geografica = partner.movilidad_geografica
            self.representante_legal_vat = partner.representante_legal_vat
            self.situacion_familiar = partner.situacion_familiar
            self.nif_conyuge = partner.nif_conyuge
            self.contrato_o_relacion = partner.contrato_o_relacion
            self.hijos_y_descendientes_m = partner.hijos_y_descendientes_m
            self.hijos_y_descendientes_m_entero = partner.hijos_y_descendientes_m_entero
            self.hijos_y_descendientes = partner.hijos_y_descendientes
            self.hijos_y_descendientes_entero = partner.hijos_y_descendientes_entero
            self.computo_primeros_hijos_1 = partner.computo_primeros_hijos_1
            self.computo_primeros_hijos_2 = partner.computo_primeros_hijos_2
            self.computo_primeros_hijos_3 = partner.computo_primeros_hijos_3
            self.hijos_y_desc_discapacidad_33 = partner.hijos_y_desc_discapacidad_33
            self.hijos_y_desc_discapacidad_entero_33 = (
                partner.hijos_y_desc_discapacidad_entero_33
            )
            self.hijos_y_desc_discapacidad_mr = partner.hijos_y_desc_discapacidad_mr
            self.hijos_y_desc_discapacidad_entero_mr = (
                partner.hijos_y_desc_discapacidad_entero_mr
            )
            self.hijos_y_desc_discapacidad_66 = partner.hijos_y_desc_discapacidad_66
            self.hijos_y_desc_discapacidad_entero_66 = (
                partner.hijos_y_desc_discapacidad_entero_66
            )
            self.ascendientes = partner.ascendientes
            self.ascendientes_entero = partner.ascendientes_entero
            self.ascendientes_m75 = partner.ascendientes_m75
            self.ascendientes_entero_m75 = partner.ascendientes_entero_m75
            self.ascendientes_discapacidad_33 = partner.ascendientes_discapacidad_33
            self.ascendientes_discapacidad_entero_33 = (
                partner.ascendientes_discapacidad_entero_33
            )
            self.ascendientes_discapacidad_mr = partner.ascendientes_discapacidad_mr
            self.ascendientes_discapacidad_entero_mr = (
                partner.ascendientes_discapacidad_entero_mr
            )
            self.ascendientes_discapacidad_66 = partner.ascendientes_discapacidad_66
            self.ascendientes_discapacidad_entero_66 = (
                partner.ascendientes_discapacidad_entero_66
            )

            if self.aeat_perception_key_id:
                self.aeat_perception_subkey_id = False
        else:
            self.partner_vat = False
            self.codigo_provincia = False

    @api.onchange("aeat_perception_key_id")
    def onchange_aeat_perception_key_id(self):
        if self.aeat_perception_key_id:
            self.aeat_perception_subkey_id = False
