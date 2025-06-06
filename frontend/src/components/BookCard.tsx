import { Component } from "solid-js";
import { A } from "@solidjs/router";
import StarRating from "./StarRating";
import { Book } from "../types/book";

const SUPABASE_PROJECT = "kwhyhflyyjhtbvbmtdmt";
const SUPABASE_IMG_URL = `https://${SUPABASE_PROJECT}.supabase.co/storage/v1/object/public/book-imgs`;

interface BookCardProps extends Book {
    onUpvote: (id: string, currentStars: number) => void;
}

const BookCard: Component<BookCardProps> = (props) => {
    // Compute cover image path from supabase
    const coverImgPath = `${SUPABASE_IMG_URL}/${props.id}/cover.jpg`;
    return (
        <div class="book-card bg-white rounded-2xl overflow-hidden shadow-xl
                hover:shadow-2xl transition-all duration-300
                transform hover:-translate-y-2 hover:rotate-2
                flex flex-col h-full">
            <A href={`/book/${props.id}`} class="flex flex-col h-full">
                <div class="relative aspect-[4/3] overflow-hidden">
                    <img
                        src={coverImgPath}
                        alt={props.title}
                        class="w-full h-full object-cover bg-gray-50"
                    />
                    <div class="absolute top-3 right-3">
                        <StarRating
                            stars={props.stars}
                            onUpvote={(e) => {
                                e.preventDefault();
                                props.onUpvote(props.id, props.stars);
                            }}
                        />
                    </div>
                </div>

                <div class="p-6 flex-grow flex flex-col">
                    <div class="flex-grow">
                        <h3 class="text-2xl font-comic text-kiddy-primary mb-2
                       group-hover:text-kiddy-secondary transition-colors">
                            {props.title}
                        </h3>
                        {props.theme && (
                            <p class="text-gray-600 font-rounded">
                                Theme: {props.theme}
                            </p>
                        )}
                        <p class="text-sm text-gray-500 mt-2">
                            Age Range: {props.age_range}
                        </p>
                    </div>

                    <button class="mt-6 w-full bg-kiddy-accent text-kiddy-primary
                         font-comic py-2 rounded-full transform
                         transition-transform hover:scale-105
                         shadow-md hover:shadow-lg">
                        Read Now! 📖
                    </button>
                </div>
            </A>
        </div>
    );
};

export default BookCard;