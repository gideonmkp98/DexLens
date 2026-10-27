"use client";
import Link from "next/link";
import CardImage from "@/components/CardImage";
import { CardListItem } from "@/lib/api";
export default function CardTile({
  card,
  priority = false,
}: {
  card: CardListItem;
  priority?: boolean;
}) {
  const id = card.external_id || card.id || "";
  return (
    <Link
      href={`/cards/${encodeURIComponent(id)}`}
      className="card-slab card-tile"
    >
      <div className="card-tile-art">
        <CardImage
          src={card.small_image_url || card.large_image_url}
          alt={card.name}
          priority={priority}
        />
      </div>
      <h3>{card.name}</h3>
      <div className="card-tile-meta">
        <span>{card.set_name || card.set_id || "Set onbekend"}</span>
        <span>#{card.local_id}</span>
      </div>
    </Link>
  );
}
