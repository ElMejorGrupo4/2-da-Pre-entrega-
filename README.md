# 2-da-Pre-entrega-
Exploración de datos del proyecto: elegir tema y dataset con el grupo, describir el objetivo, explorar y transformar datos con Pandas, y visualizar los datos con Pandas. 

### 3. Forecast de demanda eléctrica del MEM (CAMMESA)
- **Dataset:** Demanda histórica CAMMESA (horaria, por región), publicada en Datos Energía; enriquecer con temperatura horaria histórica vía API abierta de clima.
  - http://datos.energia.gob.ar/dataset/publicaciones-cammesa
- **Supervisado:** regresión multi-horizonte a 24 h.
- **No supervisado:** clustering de días típicos (laboral, fin de semana, ola de calor).
- **Plus IA:** API de predicción + explicador que traduce los valores SHAP a texto ("hoy el pico sube por temperatura y día laborable").
