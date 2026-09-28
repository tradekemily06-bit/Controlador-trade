"""Backward-compatible import for the broker-neutral post-demo learning bridge.

Concrete broker adapters must not depend on this module. New integrations should
import :class:`integration.post_demo_learning.PostDemoLearningBridge`.
"""

from integration.post_demo_learning import PostDemoLearningBridge

MT5PostDemoLearningBridge = PostDemoLearningBridge

__all__ = ["MT5PostDemoLearningBridge", "PostDemoLearningBridge"]
