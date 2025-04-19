import { Component } from "solid-js";
import { TbStarFilled } from "solid-icons/tb";

interface StarRatingProps {
  stars: number;
  onUpvote: (e: MouseEvent) => void;
}

const StarRating: Component<StarRatingProps> = (props) => {
  return (
      <button
          onClick={props.onUpvote}
          class="bg-white/90 backdrop-blur-sm rounded-full px-3 py-1
             flex items-center gap-1 text-kiddy-primary font-bold
             hover:bg-white transition-colors duration-200
             transform hover:scale-105 active:scale-95"
          aria-label={`${props.stars} stars`}
      >
        <TbStarFilled class="text-yellow-400" size={20} />
        <span>{props.stars}</span>
      </button>
  );
};

export default StarRating