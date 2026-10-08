export type FileKind = 'pdf' | 'image' | 'doc' | 'sheet' | 'archive'
export type FileStatus = 'organized' | 'review' | 'accepted' | 'ignored'

export const AUTO_THRESHOLD = 85

export type AnalyzedFile = {
  id: string
  original: string
  suggested: string
  kind: FileKind
  category: string[]
  confidence: number
  status: FileStatus
  docType: string
  topics: string[]
  reason: string
  size: string
  processedIn: string
  receivedAgo: string
}

export const recentActivity: AnalyzedFile[] = [
  {
    id: 'f1',
    original: 'electricity_bill_oct.pdf',
    suggested: 'Electricity_Bill_October_2026.pdf',
    kind: 'pdf',
    category: ['Finance', 'Bills'],
    confidence: 97,
    status: 'organized',
    docType: 'Invoice',
    topics: ['Electricity', 'Billing', 'October 2026'],
    reason: 'Detected utility provider, billing amount and invoice date.',
    size: '184 KB',
    processedIn: '1.2s',
    receivedAgo: '2 min ago',
  },
  {
    id: 'f2',
    original: 'IMG_20261008_WA0003.jpg',
    suggested: 'Receipt_Photo_2026-10-08.jpg',
    kind: 'image',
    category: ['Personal', 'Receipts'],
    confidence: 61,
    status: 'review',
    docType: 'Photo (WhatsApp)',
    topics: ['Handwriting', 'Receipt', 'Low light'],
    reason: 'Image shows a partial receipt next to handwritten notes. Text is blurred, so the purpose is ambiguous.',
    size: '2.4 MB',
    processedIn: '3.8s',
    receivedAgo: '6 min ago',
  },
  {
    id: 'f3',
    original: 'dbms_notes.pdf',
    suggested: 'DBMS_Normalization_Notes.pdf',
    kind: 'pdf',
    category: ['Academic', 'Computer Science'],
    confidence: 94,
    status: 'organized',
    docType: 'Lecture notes',
    topics: ['DBMS', 'Normalization', 'SQL'],
    reason: 'Covers 1NF–BCNF, functional dependencies and SQL joins in a lecture-notes structure.',
    size: '1.1 MB',
    processedIn: '2.1s',
    receivedAgo: '14 min ago',
  },
  {
    id: 'f4',
    original: 'offer_letter_final(1).docx',
    suggested: 'Offer_Letter_Northwind_2026.docx',
    kind: 'doc',
    category: ['Career', 'Offers'],
    confidence: 92,
    status: 'organized',
    docType: 'Employment letter',
    topics: ['Offer', 'Compensation', 'Northwind'],
    reason: 'Contains company letterhead, role title, joining date and salary terms.',
    size: '62 KB',
    processedIn: '0.9s',
    receivedAgo: '38 min ago',
  },
  {
    id: 'f5',
    original: 'Screenshot 2026-10-08 at 09.14.22.png',
    suggested: 'Flight_Booking_Confirmation.png',
    kind: 'image',
    category: ['Travel', 'Bookings'],
    confidence: 72,
    status: 'review',
    docType: 'Screenshot',
    topics: ['Flight', 'PNR', 'Booking'],
    reason: 'Looks like an airline booking page, but the PNR and date are cropped out.',
    size: '812 KB',
    processedIn: '2.6s',
    receivedAgo: '1 hr ago',
  },
  {
    id: 'f6',
    original: 'data_export_q3.xlsx',
    suggested: 'Q3_Sales_Export_2026.xlsx',
    kind: 'sheet',
    category: ['Work', 'Reports'],
    confidence: 89,
    status: 'organized',
    docType: 'Spreadsheet',
    topics: ['Sales', 'Q3 2026', 'Regions'],
    reason: 'Column headers include region, revenue and quarter; sheet name is “Q3”.',
    size: '348 KB',
    processedIn: '1.4s',
    receivedAgo: '2 hr ago',
  },
]

export const initialReviewQueue: AnalyzedFile[] = [
  recentActivity[1],
  recentActivity[4],
  {
    id: 'f7',
    original: 'scan_0042.pdf',
    suggested: 'Prescription_Dr_Mehta_Oct2026.pdf',
    kind: 'pdf',
    category: ['Health', 'Prescriptions'],
    confidence: 58,
    status: 'review',
    docType: 'Scanned document',
    topics: ['Medication', 'Clinic', 'Handwritten'],
    reason: 'Scan quality is low. A clinic header is visible but the patient name could not be read.',
    size: '1.9 MB',
    processedIn: '4.4s',
    receivedAgo: '3 hr ago',
  },
]

export type AuditEntry = {
  id: string
  time: string
  file: string
  kind: FileKind
  decision: string
  confidence: number
  action: 'auto' | 'review' | 'human-accept' | 'human-edit' | 'renamed'
  actionLabel: string
  movedTo?: string
}

export const auditLog: { day: string; entries: AuditEntry[] }[] = [
  {
    day: 'Today · Thu, 8 Oct 2026',
    entries: [
      {
        id: 'a1',
        time: '10:42 AM',
        file: 'invoice.pdf',
        kind: 'pdf',
        decision: 'Classified as Finance / Bills',
        confidence: 97,
        action: 'auto',
        actionLabel: 'Automatically organized',
        movedTo: '~/Documents/FileMind/Finance/Bills',
      },
      {
        id: 'a2',
        time: '10:39 AM',
        file: 'notes.pdf',
        kind: 'pdf',
        decision: 'Classified as Academic / Mathematics',
        confidence: 91,
        action: 'auto',
        actionLabel: 'Automatically organized',
        movedTo: '~/Documents/FileMind/Academic/Mathematics',
      },
      {
        id: 'a3',
        time: '10:36 AM',
        file: 'IMG_20261008_WA0003.jpg',
        kind: 'image',
        decision: 'Suggested Personal / Receipts',
        confidence: 61,
        action: 'review',
        actionLabel: 'Sent to Review Queue',
      },
      {
        id: 'a4',
        time: '10:21 AM',
        file: 'resume_v7.docx',
        kind: 'doc',
        decision: 'Suggested Career / Resumes',
        confidence: 79,
        action: 'human-accept',
        actionLabel: 'Accepted by you',
        movedTo: '~/Documents/FileMind/Career/Resumes',
      },
      {
        id: 'a5',
        time: '09:58 AM',
        file: 'archive_2.zip',
        kind: 'archive',
        decision: 'Suggested Work / Backups',
        confidence: 66,
        action: 'human-edit',
        actionLabel: 'Edited by you → Personal / Backups',
        movedTo: '~/Documents/FileMind/Personal/Backups',
      },
    ],
  },
  {
    day: 'Yesterday · Wed, 7 Oct 2026',
    entries: [
      {
        id: 'a6',
        time: '06:12 PM',
        file: 'signals_lab4.pdf',
        kind: 'pdf',
        decision: 'Classified as Academic / Electronics',
        confidence: 93,
        action: 'renamed',
        actionLabel: 'Renamed & organized',
        movedTo: '~/Documents/FileMind/Academic/Electronics',
      },
      {
        id: 'a7',
        time: '02:47 PM',
        file: 'rent_receipt_sep.pdf',
        kind: 'pdf',
        decision: 'Classified as Finance / Rent',
        confidence: 96,
        action: 'auto',
        actionLabel: 'Automatically organized',
        movedTo: '~/Documents/FileMind/Finance/Rent',
      },
    ],
  },
]

export type SearchResult = {
  id: string
  name: string
  kind: FileKind
  category: string[]
  match: number
  topics: string[]
  explanation: string
  location: string
  modified: string
}

export const searchResults: SearchResult[] = [
  {
    id: 's1',
    name: 'Fourier_Transforms_Notes.pdf',
    kind: 'pdf',
    category: ['Academic', 'Mathematics'],
    match: 96,
    topics: ['Fourier Transform', 'Frequency Domain'],
    explanation:
      'Matched because the document discusses Fourier transform properties and frequency-domain analysis.',
    location: '~/Documents/FileMind/Academic/Mathematics',
    modified: '12 Sep 2026',
  },
  {
    id: 's2',
    name: 'Signals_and_Systems_Lab_4.pdf',
    kind: 'pdf',
    category: ['Academic', 'Electronics'],
    match: 84,
    topics: ['DFT', 'Spectrum', 'Sampling'],
    explanation: 'Lab report applies the discrete Fourier transform to sampled audio signals.',
    location: '~/Documents/FileMind/Academic/Electronics',
    modified: '7 Oct 2026',
  },
  {
    id: 's3',
    name: 'Laplace_vs_Fourier_Cheatsheet.png',
    kind: 'image',
    category: ['Academic', 'Mathematics'],
    match: 71,
    topics: ['Laplace Transform', 'Fourier Series'],
    explanation: 'Text recognized in the image compares Laplace and Fourier transform pairs.',
    location: '~/Documents/FileMind/Academic/Mathematics',
    modified: '28 Aug 2026',
  },
]

export const fileCategories = [
  { name: 'Finance', count: 38, sub: 'Bills · Rent · Taxes' },
  { name: 'Academic', count: 52, sub: 'Mathematics · CS · Electronics' },
  { name: 'Work', count: 21, sub: 'Reports · Decks' },
  { name: 'Career', count: 7, sub: 'Offers · Resumes' },
  { name: 'Travel', count: 5, sub: 'Bookings · Visas' },
  { name: 'Personal', count: 4, sub: 'Receipts · Backups' },
]
