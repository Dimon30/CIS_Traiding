import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { DemoApp } from "@/app/DemoApp"
import "@/styles.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DemoApp />
  </StrictMode>,
)
