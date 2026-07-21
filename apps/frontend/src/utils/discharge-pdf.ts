export interface PdfSlice {
  sourceY: number;
  sourceHeight: number;
  renderedHeightMm: number;
}

export function calculatePdfSlices(
  canvasWidth: number,
  canvasHeight: number,
  contentWidthMm = 190,
  contentHeightMm = 277,
): PdfSlice[] {
  if (canvasWidth <= 0 || canvasHeight <= 0) return [];
  const millimetersPerPixel = contentWidthMm / canvasWidth;
  const maxSliceHeight = Math.max(1, Math.floor(contentHeightMm / millimetersPerPixel));
  const slices: PdfSlice[] = [];
  for (let sourceY = 0; sourceY < canvasHeight; sourceY += maxSliceHeight) {
    const sourceHeight = Math.min(maxSliceHeight, canvasHeight - sourceY);
    slices.push({ sourceY, sourceHeight, renderedHeightMm: sourceHeight * millimetersPerPixel });
  }
  return slices;
}

export async function exportDischargeElementToPdf(element: HTMLElement, filename: string) {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ]);
  const canvas = await html2canvas(element, {
    backgroundColor: '#ffffff',
    scale: 2,
    useCORS: true,
    logging: false,
  });
  const slices = calculatePdfSlices(canvas.width, canvas.height);
  if (!slices.length) throw new Error('出院小结没有可导出的内容');

  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
  slices.forEach((slice, index) => {
    if (index > 0) pdf.addPage();
    const pageCanvas = document.createElement('canvas');
    pageCanvas.width = canvas.width;
    pageCanvas.height = slice.sourceHeight;
    const context = pageCanvas.getContext('2d');
    if (!context) throw new Error('浏览器无法创建 PDF 画布');
    context.drawImage(
      canvas,
      0,
      slice.sourceY,
      canvas.width,
      slice.sourceHeight,
      0,
      0,
      canvas.width,
      slice.sourceHeight,
    );
    pdf.addImage(pageCanvas.toDataURL('image/jpeg', 0.92), 'JPEG', 10, 10, 190, slice.renderedHeightMm, undefined, 'FAST');
  });
  pdf.save(filename);
}

export function dischargePdfFilename(patientName: string, patientId: string, isDraft = false) {
  const safeName = (patientName || patientId || 'patient').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 60);
  return `${safeName}_${isDraft ? '出院小结草稿' : '出院小结'}.pdf`;
}
