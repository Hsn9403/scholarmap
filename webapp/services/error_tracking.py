"""
PostHog error tracking — capture exceptions only (no page views to keep costs low).
Les alertes Slack sont gérées directement depuis PostHog (Settings → Alerting).

Usage:
    from services.error_tracking import capture_exception
    capture_exception(e, route='/analyze', researcher=name)
"""
import os
import traceback
import logging

logger = logging.getLogger(__name__)

_posthog = None


def _get_client():
    global _posthog
    if _posthog is not None:
        return _posthog

    api_key = os.getenv('POSTHOG_API_KEY', '')
    if not api_key:
        return None

    try:
        import posthog as ph
        ph.api_key = api_key
        ph.host = os.getenv('POSTHOG_HOST', 'https://eu.i.posthog.com')
        _posthog = ph
        return _posthog
    except ImportError:
        logger.warning("posthog package not installed — error tracking disabled")
        return None


def capture_exception(error: Exception, **context):
    """
    Envoie une exception à PostHog.
    N'envoie rien si POSTHOG_API_KEY est absent (dev local).

    Args:
        error: l'exception capturée
        **context: infos supplémentaires (route, researcher, task_id…)
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.capture(
            distinct_id='server',
            event='$exception',
            properties={
                '$exception_type': type(error).__name__,
                '$exception_message': str(error),
                '$exception_traceback': traceback.format_exc(),
                **context,
            }
        )
    except Exception as tracking_err:
        logger.warning(f"PostHog capture failed: {tracking_err}")
