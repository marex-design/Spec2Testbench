#!/bin/bash

echo "========================================="
echo "🧪 TEST DE TOUS LES CIRCUITS BENCHMARK"
echo "========================================="
echo ""

RESULTS_DIR="final_test_results"
mkdir -p "$RESULTS_DIR"

TOTAL=0
PASSED=0
FAILED=0
ERROR=0

# Fichier de rapport
REPORT="$RESULTS_DIR/global_report.md"
cat > "$REPORT" << 'HEADER'
# Rapport des Tests Benchmark

| Circuit | Type | Success Rate | Métriques |
|---------|------|--------------|-----------|
HEADER

# Tester chaque circuit avec mesures
for netlist in benchmark_netlists/benchmark_netlists_with_meas/*.spice; do
    if [ ! -f "$netlist" ]; then
        continue
    fi
    
    name=$(basename "$netlist" _with_meas.spice)
    TOTAL=$((TOTAL + 1))
    
    # Déterminer le type et la spec
    if [[ "$name" == *"amplifier"* ]] || [[ "$name" == *"opamp"* ]] || [[ "$name" == *"amp"* ]]; then
        SPEC="amplifier_spec.yaml"
        TYPE="amplifier"
    elif [[ "$name" == *"filter"* ]]; then
        SPEC="filter_spec.yaml"
        TYPE="filter"
    elif [[ "$name" == *"oscillator"* ]] || [[ "$name" == *"vco"* ]]; then
        SPEC="oscillator_spec.yaml"
        TYPE="oscillator"
    elif [[ "$name" == *"mirror"* ]] || [[ "$name" == *"current"* ]]; then
        SPEC="current_mirror_spec.yaml"
        TYPE="current_mirror"
    elif [[ "$name" == *"comparator"* ]] || [[ "$name" == *"trigger"* ]]; then
        SPEC="comparator_spec.yaml"
        TYPE="comparator"
    elif [[ "$name" == *"reference"* ]] || [[ "$name" == *"bandgap"* ]]; then
        SPEC="reference_spec.yaml"
        TYPE="reference"
    else
        SPEC="general_spec.yaml"
        TYPE="general"
    fi
    
    echo "🔬 [$TOTAL] Test: $name ($TYPE)"
    
    # Exécuter le test
    output_file="$RESULTS_DIR/${name}_output.txt"
    spec2testbench verify \
        --specs "benchmark_specs/$SPEC" \
        --netlist "$netlist" \
        --no-llm --format console > "$output_file" 2>&1
    
    # Extraire le taux de succès
    if grep -q "Success Rate: 100.0%" "$output_file"; then
        echo "  ✅ PASS (100%)"
        PASSED=$((PASSED + 1))
        STATUS="✅ PASS"
        RATE="100%"
    elif grep -q "Success Rate:" "$output_file"; then
        RATE=$(grep "Success Rate:" "$output_file" | sed 's/.*Success Rate: \([0-9.]*\).*/\1/')
        echo "  ⚠️ PARTIEL ($RATE%)"
        STATUS="⚠️ PARTIEL"
    else
        echo "  ❌ FAIL/ERROR"
        FAILED=$((FAILED + 1))
        STATUS="❌ FAIL"
        RATE="0%"
    fi
    
    # Extraire les métriques
    metrics=$(grep -E "✅ PASS|❌ FAIL" "$output_file" | head -3 | awk '{print $2}' | tr '\n' ', ' | sed 's/,$//')
    
    echo "| $name | $TYPE | $RATE | $metrics |" >> "$REPORT"
    echo ""
done

echo "========================================="
echo "📊 RÉSUMÉ FINAL"
echo "========================================="
echo "Total circuits testés: $TOTAL"
echo "✅ Pass complets: $PASSED"
echo "⚠️ Partiels: $((TOTAL - PASSED - FAILED - ERROR))"
echo "❌ Fail/Error: $FAILED"
echo ""
echo "📁 Résultats: $RESULTS_DIR/"
echo "📄 Rapport: $REPORT"
echo "========================================="
