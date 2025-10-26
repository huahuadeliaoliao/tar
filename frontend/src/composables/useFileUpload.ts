/**
 * File upload composable.
 */

import { ref } from 'vue'
import { filesApi } from '@/api'
import { convertPdfToImages } from '@/utils/pdfConverter'
import type { FileAttachment } from '@/types/chat'

export function useFileUpload() {
  const uploading = ref(false)
  const uploadProgress = ref<Map<string, number>>(new Map())

  /**
   * Upload a single file to the backend.
   */
  async function uploadFile(fileAttachment: FileAttachment & { _file?: File }): Promise<number> {
    if (!fileAttachment._file) {
      throw new Error('File object not found')
    }

    const file = fileAttachment._file

    try {
      // Convert PDFs to images on the client.
      if (fileAttachment.type === 'pdf') {
        const images = await convertPdfToImages(file)
        const response = await filesApi.upload(file, images)
        return response.file_id
      }

      // Upload every other file type directly.
      const response = await filesApi.upload(file)

      // DOCX/PPT files require asynchronous processing in the backend.
      if (fileAttachment.type === 'docx' || fileAttachment.type === 'pptx') {
        await waitForProcessing(response.file_id)
      }

      return response.file_id
    } catch (error) {
      console.error('File upload failed:', error)
      throw error
    }
  }

  /**
   * Poll until the backend finishes processing the document.
   */
  async function waitForProcessing(fileId: number, maxRetries = 30): Promise<void> {
    for (let i = 0; i < maxRetries; i++) {
      const status = await filesApi.getStatus(fileId)

      if (status.processing_status === 'completed') {
        return
      }

      if (status.processing_status === 'failed') {
        throw new Error(status.error_message || '文件处理失败')
      }

      // Retry every two seconds.
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }

    throw new Error('文件处理超时')
  }

  /**
   * Upload multiple files and return their ids.
   */
  async function uploadFiles(
    fileAttachments: (FileAttachment & { _file?: File })[],
  ): Promise<number[]> {
    uploading.value = true

    try {
      const uploadPromises = fileAttachments.map((file) => uploadFile(file))
      const fileIds = await Promise.all(uploadPromises)
      return fileIds
    } finally {
      uploading.value = false
    }
  }

  return {
    uploading,
    uploadProgress,
    uploadFile,
    uploadFiles,
  }
}
