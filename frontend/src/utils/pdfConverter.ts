/**
 * PDF-to-image utilities powered by pdfjs-dist.
 */

import * as pdfjsLib from 'pdfjs-dist'

// Configure the worker path.
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`

/**
 * Convert a PDF file into an array of image Files.
 */
export async function convertPdfToImages(file: File): Promise<File[]> {
  try {
    // Load the PDF into memory.
    const arrayBuffer = await file.arrayBuffer()

    // Load and parse the PDF.
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer })
    const pdf = await loadingTask.promise

    const images: File[] = []

    // Render every page.
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum)

      // Use a higher scale for better output quality.
      const scale = 2.0 // Two-times zoom keeps text sharp.
      const viewport = page.getViewport({ scale })

      // Create a canvas for rasterization.
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')

      if (!context) {
        throw new Error('无法创建canvas context')
      }

      canvas.height = viewport.height
      canvas.width = viewport.width

      // Render the current page into the canvas.
      const renderContext = {
        canvasContext: context,
        viewport: viewport,
        canvas: canvas,
      }

      await page.render(renderContext).promise

      // Convert the canvas to a Blob.
      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, 'image/png', 0.95)
      })

      if (!blob) {
        throw new Error(`第${pageNum}页转换失败`)
      }

      // Build a File object to send downstream.
      const imageFile = new File([blob], `${file.name.replace('.pdf', '')}-page-${pageNum}.png`, {
        type: 'image/png',
      })

      images.push(imageFile)
    }

    return images
  } catch (error) {
    console.error('PDF转换失败:', error)
    throw new Error(`PDF转换失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}
