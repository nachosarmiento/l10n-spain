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

ERR_RE = re.compile(r'^(1104|1117|1157|2024|3000|3002)\b')

def _clean_err(val):
    if not val:
        return None
    s = str(val).strip().strip('"').strip("'")
    if s.lower() in ("false", "none", "null", "ninguno"):
        return None
    if ERR_RE.match(s):
        return s[:180]
    return None

def _load_csv(env, filename):
    path = get_module_resource("l10n_es_aeat_sii_oca", "migrations", "18.0.0.0.0", filename)
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
        dest = MAP.get(src)
        if not dest:
            continue
        err = _clean_err(r.get("aeat_send_error") or r.get("error") or "")
        rid = (r.get("id") or "").strip()
        if rid.isdigit():
            by_id[int(rid)] = (cid, dest, err)
        name = (r.get("name") or "").strip()
        if name:
            by_name[(cid, name)] = (dest, err)
        ref = (r.get("ref") or r.get("reference") or "").strip()
        if ref:
            by_ref[(cid, ref)] = (dest, err)
    return {"by_id": by_id, "by_name": by_name, "by_ref": by_ref}

def _apply(env, mapping, move_types):
    upd_state = upd_err = 0
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
                cid, dest_state, err_txt = idmap.get(m.id, (None, None, None))
                if cid and cid != m.company_id.id:
                    continue
                vals = {}
                if dest_state and m.aeat_state != dest_state:
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip() or None
                    if err_txt != cur:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
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
                dest_state, err_txt = by_name.get((m.company_id.id, m.name), (None, None))
                vals = {}
                if dest_state and m.aeat_state != dest_state:
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip() or None
                    if err_txt != cur:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
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
                ("ref", "in", refs),
            ])
            for m in moves:
                if m.id in updated_ids:
                    continue
                dest_state, err_txt = by_ref.get((m.company_id.id, m.ref), (None, None))
                vals = {}
                if dest_state and m.aeat_state != dest_state:
                    vals["aeat_state"] = dest_state
                    upd_state += 1
                if "aeat_send_error" in m._fields:
                    cur = (m.aeat_send_error or "").strip() or None
                    if err_txt != cur:
                        vals["aeat_send_error"] = err_txt or False
                        upd_err += 1
                if vals:
                    m.write(vals)
                    updated_ids.add(m.id)
    return upd_state, upd_err

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sales = _load_csv(env, "o16_aeat_states.csv")
    purchases = _load_csv(env, "o16_in_aeat_states.csv")
    s1, e1 = _apply(env, sales, ["out_invoice", "out_refund"])
    s2, e2 = _apply(env, purchases, ["in_invoice", "in_refund"])
    _logger.info("AEAT migration: states updated %s, errors updated %s", s1 + s2, e1 + e2)
