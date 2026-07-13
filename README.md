# Motor de Valoración y Reservas Actuariales de Vida

# 📠 Motor de Valoración y Reservas Actuariales de Vida

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B.svg)
![Pandas](https://img.shields.io/badge/Pandas-Data_Analysis-150458.svg)
![Plotly](https://img.shields.io/badge/Plotly-Data_Visualization-3F4F75.svg)

## 📌 Descripción del Proyecto
Este proyecto es un dashboard interactivo desarrollado en Python y Streamlit diseñado para la valoración técnica y el cálculo dinámico de **Reservas Matemáticas** para productos tradicionales de seguros de vida individual.

La herramienta automatiza la extracción de valores conmutativos desde tablas de mortalidad biométricas y permite proyectar la evolución del riesgo a lo largo del ciclo de vida de la póliza, auditando la consistencia matemática entre enfoques de valoración.

## ⚙️ Características Principales
* **Motor Multimodalidad:** Soporte para Seguros de Vida Entera, Temporales, Dotales Puros y Dotales Mixtos (Endowments).
* **Flexibilidad de Financiación:** Cálculo de Primas Puras Únicas (PPU), Primas Niveladas Anuales (PPA) y Primas Fraccionadas mediante la aproximación de Woolhouse.
* **Conciliación de Reservas:** Ejecución paralela y validación diferencial ($= 0$) entre el **Método Prospectivo** (obligaciones futuras) y el **Método Retrospectivo** (acumulación histórica).
* **Visualización Dinámica:** Renderizado de las curvas de capitalización y desgaste de la reserva en el tiempo mediante `Plotly`.

## 🧮 Fundamento Matemático
El motor lógico opera bajo las ecuaciones actuariales clásicas de conmutativos evaluadas en la edad alcanzada $x+t$.

### Método Prospectivo (Ejemplo: Vida Entera con Pagos Limitados a $m$ años)
La reserva en el año $t$ se define como el valor presente de los beneficios futuros menos el valor presente de las primas futuras:

$$ _tV_x = \frac{M_{x+t}}{D_{x+t}} - P \cdot \frac{N_{x+t} - N_{x+m}}{D_{x+t}} $$

*(Si $t \ge m$, el componente de primas futuras es nulo).*

## 🚀 Instalación y Ejecución Local

1. Clona el repositorio:
   ```bash
   git clone [https://github.com/tu-usuario/cotizador-reservas-actuariales.git](https://github.com/tu-usuario/cotizador-reservas-actuariales.git)
   cd cotizador-reservas-actuariales
