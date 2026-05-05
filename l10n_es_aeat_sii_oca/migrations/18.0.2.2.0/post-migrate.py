# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Corrige la inconsistencia: facturas con sii_csv registrado pero
    aeat_state = 'not_sent'. Sucede cuando la migración desde Odoo 16 copió
    la columna sii_csv (mismo nombre) pero no pudo restaurar el estado porque
    los ficheros CSV de exportación del sistema origen no estaban disponibles.
    """
    cr.execute("""
        UPDATE account_move
           SET aeat_state = 'sent'
         WHERE sii_csv IS NOT NULL AND sii_csv != ''
           AND aeat_state = 'not_sent'
           AND state = 'posted'
           AND move_type IN ('out_invoice','out_refund','in_invoice','in_refund')
    """)
    posted = cr.rowcount

    cr.execute("""
        UPDATE account_move
           SET aeat_state = 'cancelled'
         WHERE sii_csv IS NOT NULL AND sii_csv != ''
           AND aeat_state = 'not_sent'
           AND state = 'cancel'
           AND move_type IN ('out_invoice','out_refund','in_invoice','in_refund')
    """)
    cancelled = cr.rowcount

    _logger.info(
        "Migración 18.0.2.2.0 SII: corregidas %s facturas posted → 'sent', "
        "%s facturas cancel → 'cancelled'",
        posted, cancelled,
    )
