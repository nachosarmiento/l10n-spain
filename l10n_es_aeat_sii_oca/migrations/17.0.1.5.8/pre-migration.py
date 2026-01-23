# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def migrate(cr, version):
    if not version:
        return
    # Deactivate duplicate reconcile models to allow unique constraint
    cr.execute(
        """
        UPDATE account_reconcile_model arm
           SET active = false
         WHERE arm.active IS DISTINCT FROM false
           AND arm.id NOT IN (
                SELECT max(id)
                  FROM account_reconcile_model
                 GROUP BY name, company_id
           )
        """
    )
