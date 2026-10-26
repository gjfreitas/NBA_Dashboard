import { PageHeader } from "@/components/PageHeader";
import { Scoreboard } from "@/components/Scoreboard";
import { ScoresKicker } from "@/components/ScoresKicker";

export default function Home() {
  return (
    <>
      <PageHeader kicker={<ScoresKicker />} title="Scores" />
      <Scoreboard />
    </>
  );
}
