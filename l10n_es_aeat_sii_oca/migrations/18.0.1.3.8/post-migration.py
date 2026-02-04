import csv
import os
import re
import logging

from odoo import api, SUPERUSER_ID
from odoo.modules.module import get_module_resource

_logger = logging.getLogger(__name__)

MAP = {
    "not_sent": "not_sent",
    "sent": "sent",
    "sent_w_errors": "sent_w_errors",
    "sent_modified": "sent_modified",
    "cancelled": "cancelled",
    "cancelled_modified": "cancelled_modified",
}

ERR_RE = re.compile(r'^\d{3,4}\b')

def _clean_err(val):
    if not val:
        return None
    s = str(val).strip().strip('"').strip("'")
    if s.lower() in ("false", "none", "null", "ninguno"):
        return None
    return s[:180] if ERR_RE.match(s) else None

def _load_csv(env, filename):
    path = get_module_resource("l10n_es_aeat_sii_oca", "migrations", "18.0.1.0.0", filename)
    if not path or not os.path.exists(path):
        return {"by_id": {}, "by_name": {}, "by_ref": {}}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id, by_name, by_ref = {}, {}, {}
    for r in rows:
        try:
            cid = int((r.get("company_id") or "").strip() or 0)
        except Exception:
            continue
        src = (r.get("src_state") or r.get("aeat_state") or r.get("sii_state") or "").strip()
        if not cid or not src:
            continue
        dest = MAP.get(src, src)
        if not dest:
            continue
        err = _clean_err(r.get("aeat_send_error") or r.get("sii_send_error") or "")
        header_sent = r.get("aeat_header_sent") or r.get("sii_header_sent") or ""
        content_sent = r.get("aeat_content_sent") or r.get("sii_content_sent") or ""
        header_sent = header_sent if (header_sent or "").strip() else None
        content_sent = content_sent if (content_sent or "").strip() else None
        rid = (r.get("id") or r.get("move_id") or "").strip()
        if rid.isdigit():
            by_id[int(rid)] = (cid, dest, err, header_sent, content_sent)
        name = (r.get("name") or "").strip()
        if name:
            by_name[(cid, name)] = (dest, err, header_sent, content_sent)
        ref = (r.get("ref") or r.get("reference") or "").strip()
        if ref:
            by_ref[(cid, ref)] = (dest, err, header_sent, content_sent)
        payref = (r.get("payment_reference") or r.get("payment_ref") or "").strip()
        if payref:
            by_ref[(cid, payref)] = (dest, err, header_sent, content_sent)
    return {"by_id": by_id, "by_name": by_name, "by_ref": by_ref}

# NUEVO: fusiona varias fuentes; la primera tiene prioridad
def _merge_mappings(*mappings):
    res = {"by_id": {}, "by_name": {}, "by_ref": {}}
    for m in mappings:
        for k in ("by_id", "by_name", "by_ref"):
            # no sobrescribimos claves ya puestas (prioridad a la primera fuente)
            for key, val in m.get(k, {}).items():
                if key not in res[k]:
                    res[k][key] = val
    return res

def _load_csv_merge(env, *filenames):
    maps = []
    for fn in filenames:
        maps.append(_load_csv(env, fn))
    return _merge_mappings(*maps)

# NUEVO: regla de actualización
def _should_update_state(current, new):
    cur = (current or "").strip()
    newv = (new or "").strip()
    if not newv:
        return False
    # permitimos sobrescribir si está vacío o venía como 'not_sent'
    return cur in ("", "not_sent")

def _split_vals(val):
    if not val:
        return (None, None, None, None, None)
    if len(val) == 3:
        cid, dest, err = val
        return (cid, dest, err, None, None)
    if len(val) == 4:
        cid, dest, err, header = val
        return (cid, dest, err, header, None)
    if len(val) == 5:
        return val
    # fallback: ignore extra values
    return val[:5]

def _apply(env, mapping, move_types):
    upd_state = upd_err = upd_payload = 0
    updated_ids = set()

    idmap = mapping.get("by_id", {})
    if idmap:
        ids = [i for i in idmap.keys() if isinstance(i, int)]
        if ids:
            moves = env["account.move"].with_context(active_test=False).search([
                ("id", "in", ids),
                ("move_type", "in", move_types),
            ])
            for m in moves:
                cid, dest_state, err_txt, header_sent, content_sent = _split_vals(idmap.get(m.id))
                if cid and cid != m.company_id.id:
                    continue
                vals = {}
                if dest_state and _should_update_state(m.aeat_state, dest_state):
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip()
                    if (not cur) and err_txt:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
                if "aeat_header_sent" in m._fields:
                    cur = (m.aeat_header_sent or "").strip()
                    if (not cur) and header_sent:
                        vals["aeat_header_sent"] = header_sent
                        upd_payload += 1
                if "aeat_content_sent" in m._fields:
                    cur = (m.aeat_content_sent or "").strip()
                    if (not cur) and content_sent:
                        vals["aeat_content_sent"] = content_sent
                        upd_payload += 1
                if vals:
                    m.write(vals)
                    updated_ids.add(m.id)

    by_name = mapping.get("by_name", {})
    if by_name:
        companies = list({k[0] for k in by_name})
        names = list({k[1] for k in by_name})
        if companies and names:
            moves = env["account.move"].with_context(active_test=False).search([
                ("move_type", "in", move_types),
                ("company_id", "in", companies),
                ("name", "in", names),
            ])
            for m in moves:
                if m.id in updated_ids:
                    continue
                _, dest_state, err_txt, header_sent, content_sent = _split_vals(by_name.get((m.company_id.id, m.name)))
                vals = {}
                if dest_state and _should_update_state(m.aeat_state, dest_state):
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip()
                    if (not cur) and err_txt:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
                if "aeat_header_sent" in m._fields:
                    cur = (m.aeat_header_sent or "").strip()
                    if (not cur) and header_sent:
                        vals["aeat_header_sent"] = header_sent
                        upd_payload += 1
                if "aeat_content_sent" in m._fields:
                    cur = (m.aeat_content_sent or "").strip()
                    if (not cur) and content_sent:
                        vals["aeat_content_sent"] = content_sent
                        upd_payload += 1
                if vals:
                    m.write(vals)
                    updated_ids.add(m.id)

    by_ref = mapping.get("by_ref", {})
    if by_ref:
        companies = list({k[0] for k in by_ref})
        refs = list({k[1] for k in by_ref})
        if companies and refs:
            moves = env["account.move"].with_context(active_test=False).search([
                ("move_type", "in", move_types),
                ("company_id", "in", companies),
                "|", ("ref", "in", refs),
                     ("payment_reference", "in", refs),
            ])
            for m in moves:
                if m.id in updated_ids:
                    continue
                key = (m.company_id.id, m.ref) if (m.company_id.id, m.ref) in by_ref else (m.company_id.id, m.payment_reference)
                _, dest_state, err_txt, header_sent, content_sent = _split_vals(by_ref.get(key))
                vals = {}
                if dest_state and _should_update_state(m.aeat_state, dest_state):
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip()
                    if (not cur) and err_txt:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
                if "aeat_header_sent" in m._fields:
                    cur = (m.aeat_header_sent or "").strip()
                    if (not cur) and header_sent:
                        vals["aeat_header_sent"] = header_sent
                        upd_payload += 1
                if "aeat_content_sent" in m._fields:
                    cur = (m.aeat_content_sent or "").strip()
                    if (not cur) and content_sent:
                        vals["aeat_content_sent"] = content_sent
                        upd_payload += 1
                if vals:
                    m.write(vals)
                    updated_ids.add(m.id)

    return upd_state, upd_err, upd_payload

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Prioridad: CSV unificado completo si existe (o16_all_aeat_states.csv),
    # luego específicos por tipo (v2 / out/in) y finalmente legacy.
    all_states = _load_csv_merge(
        env,
        "o16_all_aeat_states_with_sent.csv",
        "o16_all_aeat_states.csv",
    )
    sales = _load_csv_merge(
        env,
        "o16_out_aeat_states_v2.csv",   # nuevo (export directo 16)
        "o16_out_aeat_states.csv",      # legacy
        "o16_aeat_states.csv",          # legacy alternativo
        "sii_errors_clientes_v16.csv",  # dataset antiguo (complemento)
    )
    purchases = _load_csv_merge(
        env,
        "o16_in_aeat_states_v2.csv",    # nuevo (export directo 16)
        "o16_in_aeat_states.csv",       # legacy
    )
    # Fusionamos dando prioridad al CSV completo si existe; no se pisa lo ya
    # cargado de fuentes anteriores.
    sales = _merge_mappings(all_states, sales)
    purchases = _merge_mappings(all_states, purchases)

    s1, e1, p1 = _apply(env, sales, ["out_invoice", "out_refund"])
    s2, e2, p2 = _apply(env, purchases, ["in_invoice", "in_refund"])
    _logger.info(
        "AEAT migration: states updated %s, errors updated %s, payloads updated %s",
        s1 + s2, e1 + e2, p1 + p2
    )
