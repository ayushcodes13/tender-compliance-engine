import TenderMvpPage from "../tender-mvp";

export const metadata = { title: "New review" };
export const maxDuration = 60;

export default function NewReviewPage() {
  return <TenderMvpPage startAtUpload />;
}
