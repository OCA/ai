class TrackingDisabledMixin:
    """Disable tracking for the whole test environment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Avoid chatter/metadata tracking interfering with assertions.
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
