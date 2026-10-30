from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from medication.models import Medication, Medication_Name, Leaflet, Active_Ingredient


class StaffCatalogTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='responsavel', email='staff@example.com', password='TestPassword42', is_staff=True)
        self.patient = User.objects.create_user(username='paciente', email='patient@example.com', password='TestPassword42')
        self.payload = {
            'medication_id': 123456789, 'process_num': '12345678901234567',
            'name': 'Medicamento de teste', 'brand': None, 'company': 'Fabricante de teste',
            'category': 'GENÉRICO', 'therapeutic_class': 'Classe de teste',
            'active_ingredients': [{'active_ingredient': 'Ingrediente de teste'}],
            'leaflet': {'indicacoes_para_uso': 'Indicações de teste', 'quando_nao_usar': 'Contraindicações de teste',
                        'como_usar_medicamento': 'Uso de teste', 'efeitos_colaterais': 'Reações de teste'},
        }
        self.client.force_authenticate(self.staff)

    def create_medication(self):
        response = self.client.post('/medication/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_staff_creates_medication_and_leaflet_and_reads_exact_process(self):
        created = self.create_medication()
        self.assertEqual(created.data['process_num'], self.payload['process_num'])
        self.assertEqual(created.data['leaflet']['como_usar_medicamento'], 'Uso de teste')
        self.assertEqual(Medication.objects.count(), 1)
        self.assertEqual(Leaflet.objects.count(), 1)
        self.client.force_authenticate(self.patient)
        response = self.client.get('/medication/?search=Ingrediente')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['leaflet']['indicacoes_para_uso'], 'Indicações de teste')

    def test_patient_cannot_create_update_or_delete(self):
        self.create_medication()
        self.client.force_authenticate(self.patient)
        self.assertEqual(self.client.post('/medication/', self.payload, format='json').status_code, 403)
        self.assertEqual(self.client.patch('/medication/123456789/', {'name': 'Alterado'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete('/medication/123456789/').status_code, 403)
        self.assertEqual(self.client.patch('/medication/leaflets/123456789/', {'como_usar_medicamento': 'Alterado'}, format='json').status_code, 403)
        self.assertEqual(Medication.objects.count(), 1)
        self.assertEqual(Leaflet.objects.get(pk=123456789).como_usar_medicamento, 'Uso de teste')

    def test_anonymous_cannot_create(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/medication/', self.payload, format='json').status_code, 401)
        self.assertEqual(Medication.objects.count(), 0)

    def test_superuser_can_manage_catalog(self):
        admin = User.objects.create_superuser(username='administrator', email='admin@example.com', password='TestPassword42')
        self.client.force_authenticate(admin)
        self.create_medication()

    def test_role_flags_come_from_django_user_and_cannot_be_changed_by_patient(self):
        self.patient.person.is_staff = True
        self.patient.person.is_superuser = True
        self.patient.person.save()
        self.client.force_authenticate(self.patient)
        self.assertFalse(self.client.get('/auth/me/').data['is_staff'])
        response = self.client.patch('/auth/me/', {'is_staff': True, 'is_superuser': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_staff'])
        self.assertFalse(response.data['is_superuser'])
        self.assertEqual(self.client.post('/medication/', self.payload, format='json').status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertTrue(self.client.get('/auth/me/').data['is_staff'])

    def test_staff_email_login_works_with_a_different_username(self):
        self.client.force_authenticate(None)
        response = self.client.post('/auth/login/', {'email': 'STAFF@example.com', 'password': 'TestPassword42'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['user']['is_staff'])
        self.assertIn('access', response.data['tokens'])

    def test_update_returns_fresh_leaflet_and_preserves_other_sections(self):
        self.create_medication()
        response = self.client.patch('/medication/123456789/', {'leaflet': {'como_usar_medicamento': 'Texto revisado'}, 'name': 'Nome revisado'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['leaflet']['como_usar_medicamento'], 'Texto revisado')
        self.assertEqual(response.data['leaflet']['indicacoes_para_uso'], 'Indicações de teste')
        self.assertEqual(Leaflet.objects.count(), 1)
        self.assertEqual(response.data['name'], 'Nome revisado')

    def test_duplicate_record_is_rejected(self):
        self.create_medication()
        duplicate = self.client.post('/medication/', self.payload, format='json')
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(Medication.objects.count(), 1)
        self.assertEqual(Leaflet.objects.count(), 1)

    def test_invalid_nested_content_does_not_create_partial_records(self):
        invalid = deepcopy(self.payload)
        invalid['leaflet']['como_usar_medicamento'] = {'not': 'text'}
        response = self.client.post('/medication/', invalid, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Medication.objects.count(), 0)
        self.assertEqual(Medication_Name.objects.count(), 0)
        self.assertEqual(Active_Ingredient.objects.count(), 0)

    def test_write_failure_rolls_back_medication_and_relations(self):
        with patch('medication.models.Leaflet.objects.create', side_effect=RuntimeError('Simulated write failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/medication/', self.payload, format='json')
        self.assertEqual(Medication.objects.count(), 0)
        self.assertEqual(Medication_Name.objects.count(), 0)
        self.assertEqual(Active_Ingredient.objects.count(), 0)

    def test_record_id_cannot_change_and_process_must_fit_database(self):
        self.create_medication()
        response = self.client.patch('/medication/123456789/', {'medication_id': 100}, format='json')
        self.assertEqual(response.status_code, 400)
        invalid = deepcopy(self.payload); invalid['medication_id'] = 100; invalid['process_num'] = '9223372036854775808'
        self.assertEqual(self.client.post('/medication/', invalid, format='json').status_code, 400)
        self.assertEqual(Medication.objects.count(), 1)

    def test_blank_ingredient_is_rejected_even_in_string_format(self):
        invalid = deepcopy(self.payload)
        invalid['active_ingredients'] = ['   ']
        response = self.client.post('/medication/', invalid, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Medication.objects.count(), 0)
