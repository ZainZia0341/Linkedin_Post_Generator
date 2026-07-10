import { CreatorDetailView } from "@/components/CreatorDetailView";

type CreatorDetailPageProps = {
  params: Promise<{ creatorId: string }>;
};

export default async function CreatorDetailPage({ params }: CreatorDetailPageProps) {
  const { creatorId } = await params;
  return <CreatorDetailView creatorId={decodeURIComponent(creatorId)} />;
}
