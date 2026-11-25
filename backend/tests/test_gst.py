import unittest
from app.utils.gst import compute_line_tax, compute_order_tax_summary, is_intra_state


class TestGSTUtilities(unittest.TestCase):
    def test_intra_state_determination(self):
        # Tamil Nadu (33) to Tamil Nadu (33) -> Intra-state
        self.assertTrue(is_intra_state("33", "33"))
        self.assertTrue(is_intra_state(" 33 ", "33"))
        # Tamil Nadu (33) to Karnataka (29) -> Inter-state
        self.assertFalse(is_intra_state("33", "29"))
        # Empty or None state codes
        self.assertFalse(is_intra_state("", "33"))
        self.assertFalse(is_intra_state("33", None))

    def test_benchmark_tax_calculations(self):
        # 1. 750,000 paise at 500 bp intra-state -> CGST 18,750, SGST 18,750, IGST 0
        cgst, sgst, igst = compute_line_tax(taxable_paise=750000, gst_rate_bp=500, intra_state=True)
        self.assertEqual(cgst, 18750)
        self.assertEqual(sgst, 18750)
        self.assertEqual(igst, 0)
        self.assertEqual(cgst + sgst + igst, 37500)

        # 2. 750,000 paise at 500 bp inter-state -> CGST 0, SGST 0, IGST 37,500
        cgst, sgst, igst = compute_line_tax(taxable_paise=750000, gst_rate_bp=500, intra_state=False)
        self.assertEqual(cgst, 0)
        self.assertEqual(sgst, 0)
        self.assertEqual(igst, 37500)

        # 3. 12,345 paise at 500 bp:
        # Intra-state: 12345 * 0.025 = 308.625 -> rounds half up to 309 for CGST, 309 for SGST
        cgst, sgst, igst = compute_line_tax(taxable_paise=12345, gst_rate_bp=500, intra_state=True)
        self.assertEqual(cgst, 309)
        self.assertEqual(sgst, 309)
        self.assertEqual(igst, 0)

        # Inter-state: 12345 * 0.05 = 617.25 -> rounds half up to 617 for IGST
        cgst, sgst, igst = compute_line_tax(taxable_paise=12345, gst_rate_bp=500, intra_state=False)
        self.assertEqual(cgst, 0)
        self.assertEqual(sgst, 0)
        self.assertEqual(igst, 617)

    def test_order_tax_summary(self):
        lines = [
            {"line_total_paise": 750000, "gst_rate_bp": 500},
            {"line_total_paise": 12345, "gst_rate_bp": 500},
        ]
        # Intra-state: 750000 -> 18750 + 18750; 12345 -> 309 + 309
        summary = compute_order_tax_summary(lines, "33", "33")
        self.assertTrue(summary["is_intra_state"])
        self.assertEqual(summary["taxable_amount_paise"], 762345)
        self.assertEqual(summary["cgst_paise"], 18750 + 309)
        self.assertEqual(summary["sgst_paise"], 18750 + 309)
        self.assertEqual(summary["igst_paise"], 0)
        self.assertEqual(summary["grand_total_paise"], 762345 + (18750 + 309) * 2)

        # Inter-state
        summary_inter = compute_order_tax_summary(lines, "33", "29")
        self.assertFalse(summary_inter["is_intra_state"])
        self.assertEqual(summary_inter["cgst_paise"], 0)
        self.assertEqual(summary_inter["sgst_paise"], 0)
        self.assertEqual(summary_inter["igst_paise"], 37500 + 617)
        self.assertEqual(summary_inter["grand_total_paise"], 762345 + 37500 + 617)


if __name__ == "__main__":
    unittest.main()
