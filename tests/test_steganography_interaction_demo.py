"""真实 StegoKit 三智能体隐写交互演示测试。"""

from __future__ import annotations

import importlib.util
import unittest

from stegopot.tools import bundled_stegokit_path


_HAS_STEGO_DEPENDENCIES = all(
    importlib.util.find_spec(module_name) is not None
    for module_name in ("torch", "transformers")
)
_HAS_BUNDLED_STEGOKIT = (
    bundled_stegokit_path() / "stegokit" / "__init__.py"
).is_file()


class SteganographyInteractionDemoTest(unittest.TestCase):
  """验证公共文本、私有解码结果和审计隔离。"""

  @unittest.skipUnless(
      _HAS_STEGO_DEPENDENCIES and _HAS_BUNDLED_STEGOKIT,
      "需要初始化 StegoKit 子模块并安装 stegopot[stego]",
  )
  def test_real_stegokit_hidden_interaction(self) -> None:
    """验证真实 AC 算法只向授权节点暴露秘密。"""
    from examples.steganography_interaction_demo import run_demo

    trace = run_demo("OK")

    self.assertEqual(trace.receiver_bits, trace.secret_bits)
    self.assertEqual(trace.recovered_text, "OK")
    self.assertNotIn("OK", trace.cover_text)
    self.assertNotIn("stego", trace.public_metadata)
    self.assertTrue(trace.receiver_can_decode)
    self.assertFalse(trace.auditor_can_decode)
    self.assertEqual(trace.auditor_decoded_count, 0)
    self.assertEqual(trace.public_recipients, ("auditor", "receiver"))
    self.assertEqual(trace.encoded_message_count, 1)
    self.assertEqual(trace.decoded_message_count, 1)
    self.assertGreater(len(trace.generated_token_ids), 0)
    self.assertIn("stego_embedded", trace.event_kinds)
    self.assertIn("stego_decoded", trace.event_kinds)


if __name__ == "__main__":
  unittest.main()
