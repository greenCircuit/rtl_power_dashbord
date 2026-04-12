import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Chart, registerables } from 'chart.js'
import 'bootstrap/dist/css/bootstrap.min.css'
import './index.css'
import App from './App.tsx'

// Register all Chart.js components
Chart.register(...registerables)

// Global chart defaults — dark theme
Chart.defaults.color = '#aaa'
Chart.defaults.borderColor = '#2a2a2a'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
