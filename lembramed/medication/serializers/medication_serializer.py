from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from ..models import (
    Medication, Medication_Name, Active_Ingredient,
    Brand, Therapeutic_Class, Category, Company, Leaflet
)

class MedicationNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medication_Name
        fields = ['name']


class ActiveIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Active_Ingredient
        fields = ['active_ingredient']

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = {'active_ingredient': data}
        return super().to_internal_value(data)

class CatalogLeafletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Leaflet
        fields = [
            'indicacoes_para_uso', 'funcionamento_medicamento', 'quando_nao_usar',
            'conhecimento_previo_necessario', 'como_guardar_medicamento',
            'como_usar_medicamento', 'esqueceu_medicamento', 'efeitos_colaterais',
            'quantidade_a_mais',
        ]
        extra_kwargs = {field: {'required': False, 'allow_blank': True} for field in fields}


class MedicationSerializer(serializers.ModelSerializer):
    leaflet = CatalogLeafletSerializer(required=False)
    medication_id = serializers.IntegerField(
        min_value=1, max_value=2147483647,
        validators=[UniqueValidator(queryset=Medication.objects.all(), message='Este registro já está cadastrado.')],
    )
    # Keep large regulatory numbers exact when consumed by JavaScript.
    process_num = serializers.DecimalField(max_digits=19, decimal_places=0, min_value=1,
        max_value=9223372036854775807, coerce_to_string=True)

    def validate(self, attrs):
        instance = self.instance
        if instance and 'medication_id' in attrs and attrs['medication_id'] != instance.pk:
            raise serializers.ValidationError({'medication_id': 'O registro não pode ser alterado.'})
        name = attrs.get('name', instance.name if instance else None)
        brand = attrs.get('brand', instance.brand if instance else None)
        if not name and not brand:
            raise serializers.ValidationError({'name': 'Informe o nome ou nome comercial.'})
        if (not instance or 'active_ingredients' in attrs) and not attrs.get('active_ingredients'):
            raise serializers.ValidationError({'active_ingredients': 'Informe pelo menos um princípio ativo.'})
        return attrs

    name = serializers.CharField(required=False, allow_null=True)
    category = serializers.CharField(required=False, allow_null=True)
    company = serializers.CharField(required=False, allow_null=True)
    brand = serializers.CharField(required=False, allow_null=True)
    therapeutic_class = serializers.CharField(required=False, allow_null=True)
    active_ingredients = ActiveIngredientSerializer(many=True, required=False)

    class Meta:
        model = Medication
        fields = [
            "medication_id", "process_num", "name",
            "active_ingredients", "therapeutic_class",
            "category", "brand", "company", "leaflet",
        ]
    
    def _resolve_relation(self, model_class, field_name, value):
        if not value:
            return None
        
        text = value.get(field_name) if isinstance(value, dict) else str(value).strip()
        obj, _ = model_class.objects.get_or_create(**{field_name: text})

        return obj
    
    @transaction.atomic
    def create(self, validated_data):
        leaflet = validated_data.pop('leaflet', None)
        active_ingredients_data = validated_data.pop('active_ingredients', [])
        
        name_val = validated_data.pop('name', None)
        category_val = validated_data.pop('category', None)
        company_val = validated_data.pop('company', None)
        brand_val = validated_data.pop('brand', None)
        tc_val = validated_data.pop('therapeutic_class', None)
        medication = Medication.objects.create(
            name=self._resolve_relation(Medication_Name, 'name', name_val),
            category=self._resolve_relation(Category, 'category', category_val),
            company=self._resolve_relation(Company, 'company', company_val),
            brand=self._resolve_relation(Brand, 'brand', brand_val),
            therapeutic_class=self._resolve_relation(Therapeutic_Class, 'therapeutic_class', tc_val),
            **validated_data
        )
        for ai_item in active_ingredients_data:
            ai_name = ai_item.get('active_ingredient') if isinstance(ai_item, dict) else str(ai_item)
            if ai_name:
                ai_obj, _ = Active_Ingredient.objects.get_or_create(active_ingredient=ai_name.strip())
                medication.active_ingredients.add(ai_obj)
        if leaflet is not None:
            Leaflet.objects.create(medication=medication, **leaflet)
        return medication

    @transaction.atomic
    def update(self, instance, validated_data):
        leaflet = validated_data.pop('leaflet', None)
        active_ingredients_data = validated_data.pop('active_ingredients', None)
        if 'name' in validated_data:
            instance.name = self._resolve_relation(Medication_Name, 'name', validated_data.pop('name'))
        if 'category' in validated_data:
            instance.category = self._resolve_relation(Category, 'category', validated_data.pop('category'))
        if 'company' in validated_data:
            instance.company = self._resolve_relation(Company, 'company', validated_data.pop('company'))
        if 'brand' in validated_data:
            instance.brand = self._resolve_relation(Brand, 'brand', validated_data.pop('brand'))
        if 'therapeutic_class' in validated_data:
            instance.therapeutic_class = self._resolve_relation(Therapeutic_Class, 'therapeutic_class', validated_data.pop('therapeutic_class'))
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if active_ingredients_data is not None:
            instance.active_ingredients.clear()
            for ai_item in active_ingredients_data:
                ai_name = ai_item.get('active_ingredient') if isinstance(ai_item, dict) else str(ai_item)
                if ai_name:
                    ai_obj, _ = Active_Ingredient.objects.get_or_create(active_ingredient=ai_name.strip())
                    instance.active_ingredients.add(ai_obj)
        if leaflet is not None:
            Leaflet.objects.update_or_create(medication=instance, defaults=leaflet)
            instance._state.fields_cache.pop('leaflet', None)
        return instance

    def to_representation(self, instance):
        """Format the output string representations for GET responses."""

        data = super().to_representation(instance)
        data['name'] = instance.name.name if instance.name else None
        data['category'] = instance.category.category if instance.category else None
        data['company'] = instance.company.company if instance.company else None
        data['brand'] = instance.brand.brand if instance.brand else None
        data['therapeutic_class'] = instance.therapeutic_class.therapeutic_class if instance.therapeutic_class else None
        
        return data

class TherapeuticClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Therapeutic_Class
        fields = ['therapeutic_class']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['category']

    
class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ['brand']


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['company']

