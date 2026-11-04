import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
try:
    from PyQt6.QtWidgets import QApplication
    from simulatie.venster import Venster
    QT_BESCHIKBAAR=True
except ImportError:
    QT_BESCHIKBAAR=False


@unittest.skipUnless(QT_BESCHIKBAAR,'Installeer requirements-sim.txt voor de PyQt-venstertests')
class VensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.v=Venster();self.v.timer.stop();self.v.show();self.app.processEvents()

    def tearDown(self):
        self.v.close();self.app.processEvents()

    def test_kaart_en_start_pauze_stap_reset(self):
        v=self.v
        self.assertEqual(len(v.weergave.wegen),32)
        self.assertEqual(v.doelen(),['WILDWATER','FREEFALL'])
        self.assertTrue(v.start_button.isEnabled())
        v.start_button.click();v.sim.update(500);v._ververs()
        self.assertFalse(v.start_button.isEnabled())
        v.pauze_button.click()
        self.assertTrue(v.sim.gepauzeerd)
        nu=v.sim.nu;v.stap_button.click()
        self.assertEqual(v.sim.nu,nu+100)
        v._reset();self.assertEqual(v.sim.besturing.toestand,'GEREED')
        self.assertEqual(v.stappen.count(),24)

    def test_doelen_herordenen_en_voorbeeld(self):
        v=self.v;v.bestemmingen.setCurrentRow(1);v._verplaats(-1)
        self.assertEqual(v.doelen(),['FREEFALL','WILDWATER'])
        v.preview_button.click()
        self.assertEqual(v.sim.beeld()['plan']['bestemmingen'],v.doelen())

    def test_visuele_obstakel_en_ids(self):
        v=self.v;v.start_button.click();v.sim.update(500)
        v.obstakel.setChecked(True);v.sim.update(100);v._ververs()
        self.assertEqual(v.sim.besturing.toestand,'GEBLOKKEERD')
        self.assertIn('vrij baan',v.toestand.text())
        v.ids.setChecked(True)
        self.assertTrue(all(item.isVisible() for item in v.weergave.ids.values()))

    def test_foute_opdracht_toont_reden(self):
        v=self.v
        v._actie(lambda:v.sim.start(['ONBEKEND']))
        self.assertIn('Onbekende attractie',v.bericht.text())
        self.assertEqual(v.sim.besturing.toestand,'GEREED')

    def test_tekst_heeft_een_werkelijk_lettertype(self):
        from PyQt6.QtGui import QRawFont
        lettertype=QRawFont.fromFont(self.v.toestand.font())
        self.assertTrue(lettertype.isValid())
        self.assertTrue(lettertype.supportsCharacter('P'))

    def test_routewijziging_toont_pending_en_daarna_actief(self):
        v=self.v;v.start_button.click();v.sim.update(500)
        v.bestemmingen.clear();v._voeg_id_toe('COASTER');v._ververs()
        v.wijzig_button.click()
        self.assertIn('wacht',v.bericht.text())
        v.sim.update(2500);v._ververs()
        self.assertIn('nu actief',v.bericht.text())

    def test_klein_venster_houdt_kaart_binnen_de_kaarttegel(self):
        v=self.v;v.resize(1060,730);self.app.processEvents()
        view=v.weergave
        self.assertTrue(view.parentWidget().rect().contains(view.geometry()))
        rechthoek=view.mapFromScene(view.sceneRect()).boundingRect()
        self.assertLessEqual(rechthoek.bottom(),view.viewport().height()+2)


if __name__=='__main__':unittest.main()
