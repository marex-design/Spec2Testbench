#!/bin/bash

echo "========================================="
echo "🔬 TEST DE TOUS LES FILTRES BENCHMARK"
echo "========================================="
echo ""

RESULTS_DIR="filter_test_results"
mkdir -p "$RESULTS_DIR"

TOTAL=0
PASSED=0

# Liste des filtres dans benchmark_netlists
filters=(
    "lowpass_filter"
    "highpass_filter"
    "bandpass_filter"
    "notch_filter"
)

for filter in "${filters[@]}"; do
    TOTAL=$((TOTAL + 1))
    
    # Créer une spécification générique pour ce filtre
    cat > "$RESULTS_DIR/${filter}_spec.yaml" << YAML
name: "${filter}"
circuit_type: "filter"

performance_targets:
  cutoff_frequency_hz:
    min: 100
    max: 10000000
    unit: "Hz"
YAML

    echo "🔬 [$TOTAL] Test: $filter"
    
    # Utiliser la netlist originale ou créer une version avec mesures
    if [ -f "benchmark_netlists/${filter}.cir" ]; then
        python verify_direct_v2.py "$RESULTS_DIR/${filter}_spec.yaml" "benchmark_netlists/${filter}.cir" 2>&1 | grep -E "✅|❌|Résultat"
    else
        echo "  ⚠️ Fichier non trouvé: ${filter}.cir"
    fi
    
    echo ""
done

echo "========================================="
echo "✅ Tests terminés: $TOTAL filtres traités"
echo "📁 Résultats dans: $RESULTS_DIR/"
echo "========================================="
