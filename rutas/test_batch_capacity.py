import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from openpyxl import Workbook

from rutas.services.batch_selection import read_excel
from rutas.services.documents import print_sheets


class BatchCapacityTests(SimpleTestCase):
    def workbook(self, count):
        book = Workbook()
        sheet = book.active
        sheet.append(["SHOP ORDER", "ITEM PADRE", "CANTIDAD", "SEMANA", "RE", "Secuencia"])
        for number in range(1, count + 1):
            sheet.append([f"SO-{number:03}", "PARTE-1", 1, "31A", 0, number])
        stream = io.BytesIO()
        book.save(stream)
        return SimpleUploadedFile("ordenes.xlsx", stream.getvalue())

    def test_excel_accepts_200_orders_and_rejects_201(self):
        rows = read_excel(self.workbook(200))
        self.assertEqual(len(rows), 200)
        self.assertEqual(rows[0]["shop_order"], "SO-001")
        self.assertEqual(rows[-1]["shop_order"], "SO-200")
        with self.assertRaisesRegex(ValueError, "200 órdenes"):
            read_excel(self.workbook(201))

    def test_200_labels_need_100_sheets(self):
        labels = [{"shop_order": f"SO-{number:03}", "operations": []} for number in range(1, 201)]
        sheets = print_sheets({"labels": labels, "copies": 1})
        self.assertEqual(len(sheets), 100)
        self.assertTrue(all(len(sheet) == 2 for sheet in sheets))
