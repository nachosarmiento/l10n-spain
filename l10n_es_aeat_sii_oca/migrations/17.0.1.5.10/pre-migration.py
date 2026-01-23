# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def migrate(cr, version):
    if not version:
        return
    # Remove duplicate reconcile models to allow unique constraint on (name, company_id)
    cr.execute(
        """
        DELETE FROM account_reconcile_model
         WHERE id NOT IN (
            SELECT max(id)
              FROM account_reconcile_model
             GROUP BY name, company_id
         )
        """
    )
