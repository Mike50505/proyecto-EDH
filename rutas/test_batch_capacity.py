import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from openpyxl import Workbook

from rutas.services.batch_selection import read_excel, rows_from_post
from rutas.services.documents import print_sheets


class BatchCapacityTests(SimpleTestCase):
    def workbook(self, count):
        book = Workbook()
        sheet = book.active
        sheet.append(["ITEM PADRE", "CANTIDAD", "SEMANA"])
        for number in range(1, count + 1):
            sheet.append(["PARTE-1", 1, f"{number:03}A"])
        stream = io.BytesIO()
        book.save(stream)
        return SimpleUploadedFile("ordenes.xlsx", stream.getvalue())

    def test_excel_accepts_200_orders_and_rejects_201(self):
        rows = read_excel(self.workbook(200))
        self.assertEqual(len(rows), 200)
        self.assertEqual(rows[0]["shop_order"], "001A")
        self.assertEqual(rows[-1]["shop_order"], "200A")
        self.assertEqual(rows[-1]["sequence"], "200")
        with self.assertRaisesRegex(ValueError, "200 órdenes"):
            read_excel(self.workbook(201))

    def test_previous_four_column_template_still_loads(self):
        book = Workbook()
        book.active.append(["ITEM PADRE", "CANTIDAD", "SEMANA", "RE"])
        book.active.append(["PARTE-1", 2, "31A", 99])
        stream = io.BytesIO()
        book.save(stream)
        rows = read_excel(SimpleUploadedFile("anterior.xlsx", stream.getvalue()))
        self.assertEqual(rows[0]["shop_order"], "31A")
        self.assertEqual(rows[0]["sequence"], "1")
        self.assertEqual(rows[0]["re"], "")

    def test_200_labels_need_100_sheets(self):
        labels = [{"shop_order": f"SO-{number:03}", "operations": []} for number in range(1, 201)]
        sheets = print_sheets({"labels": labels, "copies": 1})
        self.assertEqual(len(sheets), 100)
        self.assertTrue(all(len(sheet) == 2 for sheet in sheets))

    def test_post_uses_week_as_order_and_numbers_used_rows(self):
        rows = rows_from_post({
            "row_count": "3", "rows-0-parent_code": "PARTE-A", "rows-0-quantity": "2",
            "rows-0-week": "31A", "rows-0-shop_order": "IGNORAR", "rows-0-sequence": "99",
            "rows-2-parent_code": "PARTE-B", "rows-2-quantity": "3",
            "rows-2-week": "32B", "rows-2-shop_order": "IGNORAR", "rows-2-sequence": "99",
        })
        self.assertEqual([(row["shop_order"], row["sequence"]) for row in rows],
                         [("31A", "1"), ("32B", "2")])
