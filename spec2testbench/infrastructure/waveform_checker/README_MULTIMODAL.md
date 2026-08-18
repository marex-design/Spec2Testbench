# LLM Multimodal Waveform Analysis

Ce module fournit une interface haute niveau pour l'analyse multimodale de formes d'onde en utilisant les capacités de vision des LLMs modernes.

## 🚀 Démarrage Rapide

### 1. Installation

```bash
# Dépendances requises
pip install pillow>=9.0

# Optionnel : pour chaque provider
pip install openai              # OpenAI GPT-4V
pip install openai              # DeepSeek (utilise OpenAI SDK)
pip install google-generativeai # Google Gemini
pip install anthropic           # Anthropic Claude
```

### 2. Utilisation Basique

```python
from pathlib import Path
from spec2testbench.infrastructure.waveform_checker.llm_multimodal_client import LLMMultimodalClient

# Initialiser le client
client = LLMMultimodalClient(
    provider="openai",
    api_key="sk-...",
    model="gpt-4-vision"
)

# Analyser une waveform
result = client.analyze_waveform(
    image_path=Path("waveform.png"),
    circuit_type="oscillator"
)

# Résultats
print(f"Waveform type: {result.waveform_type}")
print(f"Anomalies: {result.anomalies}")
print(f"Recommendations: {result.recommendations}")
```

### 3. Intégration avec WaveformChecker

```python
from spec2testbench.infrastructure.waveform_checker import WaveformChecker

# Auto-création du LLMMultimodalClient
checker = WaveformChecker(provider="openai", api_key="sk-...")

# Analyse avancée
result = checker.analyze_with_multimodal(
    image_path=Path("waveform.png"),
    circuit_type="filter",
    failed_metrics=["gain", "phase_margin"]
)
```

## 📊 Providers Supportés

| Provider | Model | Vision | Coût | Performance |
|----------|-------|--------|------|-------------|
| **OpenAI** | GPT-4-Vision | ✅ Excellent | $$ | Très rapide |
| **DeepSeek** | DeepSeek-VL | ✅ Bon | $ | Rapide |
| **Google** | Gemini-1.5-Vision | ✅ Excellent | $ | Très rapide |
| **Anthropic** | Claude-3-Vision | ✅ Excellent | $$$ | Rapide |

### Configuration des API Keys

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# DeepSeek
export DEEPSEEK_API_KEY="sk-..."

# Google Gemini
export GOOGLE_API_KEY="..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 🎯 Cas d'Utilisation

### 1. Analyse de Waveform Complète

```python
from spec2testbench.infrastructure.waveform_checker.llm_multimodal_client import DiagnosticLevel

result = client.analyze_waveform(
    image_path=Path("oscillator_output.png"),
    circuit_type="ring_oscillator",
    expected_behavior="1 MHz sine wave with 2.5V amplitude",
    diagnostic_level=DiagnosticLevel.DETAILED
)

print(f"Type: {result.waveform_type}")
print(f"Amplitude: {result.extracted_metrics.get('amplitude')} V")
print(f"Frequency: {result.extracted_metrics.get('frequency')} Hz")
print(f"Diagnosis: {result.diagnosis}")
```

### 2. Extraction de Métriques Spécifiques

```python
metrics = client.extract_metrics(
    image_path=Path("waveform.png"),
    metrics_to_extract=["amplitude", "frequency", "rise_time", "fall_time"],
    circuit_type="amplifier"
)

for metric, value in metrics.items():
    print(f"{metric}: {value}")
```

### 3. Détection d'Anomalies avec Seuils

```python
result = client.detect_anomalies(
    image_path=Path("waveform.png"),
    circuit_type="opamp",
    thresholds={
        "amplitude": {"min": 4.8, "max": 5.2},  # 5V supply
        "rise_time": {"min": 1e-9, "max": 10e-9},  # 10 ns max
    }
)

print(f"Anomalies detected: {result['anomalies']}")
print(f"Severity: {result['severity']}")  # low, medium, high
for rec in result['recommendations']:
    print(f"  → {rec}")
```

### 4. Diagnostic d'Échec de Test

```python
diagnosis = client.diagnose_failure(
    image_path=Path("failed_test.png"),
    failed_specification={
        "amplitude": 2.0,  # Measured value
        "slew_rate": 1e4   # V/s
    },
    circuit_type="buffer_amplifier"
)

print(f"Root cause: {diagnosis['root_cause']}")
print(f"Diagnosis: {diagnosis['diagnosis']}")
for rec in diagnosis['recommendations']:
    print(f"  ✓ {rec}")
```

### 5. Optimization d'Images pour Vision LLM

```python
from spec2testbench.infrastructure.waveform_checker import WaveformChecker

checker = WaveformChecker(provider="openai")

optimized_path = checker.optimize_waveform_image(
    image_path=Path("waveform.png"),
    test_name="AC Gain Test",
    circuit_type="Op-Amp",
    specification={"gain": {"min": 60, "max": 100}},  # dB
    anomalies=["ringing", "overshoot"]
)
```

## 📝 Niveaux Diagnostiques

```python
from spec2testbench.infrastructure.waveform_checker.llm_multimodal_client import DiagnosticLevel

# QUICK - Extraction rapide des features principales
# Temps: ~1-2 sec | Tokens: ~500
result = client.analyze_waveform(
    image_path="waveform.png",
    diagnostic_level=DiagnosticLevel.QUICK
)

# STANDARD - Analyse complète avec anomalies (recommandé)
# Temps: ~2-3 sec | Tokens: ~1000
result = client.analyze_waveform(
    image_path="waveform.png",
    diagnostic_level=DiagnosticLevel.STANDARD
)

# DETAILED - Analyse exhaustive avec recommandations
# Temps: ~3-5 sec | Tokens: ~1500
result = client.analyze_waveform(
    image_path="waveform.png",
    diagnostic_level=DiagnosticLevel.DETAILED
)
```

## 🔍 Résultats d'Analyse

### WaveformDiagnosisResult

```python
result.waveform_type          # str: "sinusoidal", "square", "damped", etc.
result.features              # Dict[str, Dict]: features extraites
result.anomalies             # List[str]: anomalies détectées
result.diagnosis             # str: diagnostic en texte libre
result.recommendations       # List[str]: recommandations actionnables
result.confidence            # float: 0-1 score de confiance
result.extracted_metrics     # Dict[str, float]: métriques extraites
result.model_name            # str: nom du modèle utilisé
```

## 🎨 Types de Waveforms Reconnus

- **sinusoidal** - Onde sinusoïdale pure
- **square** - Onde carrée
- **triangular** - Onde triangulaire
- **sawtooth** - Onde en dent de scie
- **damped_oscillation** - Oscillation amortie
- **pulse** - Impulsion
- **noise** - Bruit
- **constant** - Signal constant (DC)
- **other** - Autres types

## 🔴 Anomalies Détectables

- **ringing** - Oscillations parasites
- **clipping** - Écrêtage/saturation
- **dc_drift** - Dérive de l'offset DC
- **jitter** - Gigue temporelle
- **offset_error** - Erreur d'offset
- **cross_talk** - Diaphonie
- **slew_limited** - Limité par slew rate
- **oscillation** - Oscillation entretenue
- **nonlinear_distortion** - Distorsion harmonique
- **noise** - Bruit excessif

## 💰 Estimations de Coût

| Provider | Prix/1K tokens | Analyse Typique |
|----------|-----------------|-----------------|
| OpenAI GPT-4V | $0.01 input / $0.03 output | ~$0.05 |
| DeepSeek-VL | $0.003 input / $0.009 output | ~$0.01 |
| Gemini-1.5 | $0.001 input / $0.004 output | ~$0.005 |
| Claude-3 | $0.003 input / $0.015 output | ~$0.02 |

## ⚠️ Limitations et Considérations

1. **Qualité d'image**: Les images de mauvaise qualité peuvent réduire l'accuracy
2. **Résolution**: Minimum 512x512 recommandé pour résultats fiables
3. **Contexte**: Fournir le circuit type et comportement attendu améliore les résultats
4. **Fallback**: Si vision LLM échoue, utiliser DiagnosticLevel.QUICK
5. **Rate limits**: Respecter les limites API de chaque provider
6. **Cost**: Vision LLM coûte ~10x plus cher que text-only

## 🧪 Testing

Voir `tests/test_multimodal_client.py` pour des exemples complets.

```bash
# Run all tests
python tests/test_multimodal_client.py --provider openai --api-key sk-...

# Skip LLM tests (waveform plotter only)
python tests/test_multimodal_client.py --skip-llm

# Use specific image
python tests/test_multimodal_client.py --image /path/to/waveform.png
```

## 📚 Documentation

- API Reference: `docs/api/multimodal_client.md`
- Examples: `examples/multimodal_analysis.py`
- Integration Guide: `docs/integration/waveform_checker.md`

## 🤝 Contribution

Pour ajouter un nouveau provider:

1. Implémenter méthode `_multimodal_<provider>()` dans `LLMClient`
2. Ajouter provider à enum `LLMProvider`
3. Tester avec `test_multimodal_client.py`
4. Documenter dans ce README

## 📞 Support

- **Issues**: Ouvrir une issue sur GitHub
- **Questions**: Vérifier la documentation
- **Bugs**: Fournir reproducer minimal avec trace complète
