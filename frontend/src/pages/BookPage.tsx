import { createResource, createSignal, Show } from "solid-js";
import { useParams } from "@solidjs/router";
import { bookService } from "../services/api";
import { BookSpread } from "../components/BookPage/BookSpread";
import PageControls from "../components/BookPage/PageControls";
import StarRating from "../components/StarRating";

export default function BookPage() {
    const params = useParams();
    // Guard: only fetch if params.id is defined and not 'undefined'
    const validId = params.id && params.id !== 'undefined';
    const [book, { refetch }] = createResource(() => validId ? params.id : undefined, bookService.getBook);
    const [currentPage, setCurrentPage] = createSignal(0);
    const [error, setError] = createSignal<string | null>(null);

    // Helper to extract page content and images from new structure
    const getPages = () => {
        if (!book() || !book().content || !Array.isArray(book().content.pages)) return [];
        // Insert a placeholder for the cover at index 0, then all story pages, then a placeholder for the rating/ending page
        return [""]
            .concat(book().content.pages.map(p => p.text || ""))
            .concat([""]); // for the rating/ending page
    };
    const getPageImages = () => {
        if (!book() || !book().content || !Array.isArray(book().content.pages)) return [];
        // First image is the cover, then the rest are story pages. No placeholder at the end!
        return [{ url: getCoverImage() }]
            .concat(book().content.pages.map((_, i) => ({ url:  `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${book().id}/page${i+1}.jpg` })))
    };
    const getCoverImage = () => {
        return `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${book().id}/cover.jpg`;
    };

    const handleUpvote = async (id: string, currentStars: number) => {
        try {
            await bookService.updateStars(id, currentStars);
            refetch();
        } catch (e) {
            console.error('Error updating stars:', e);
            setError(e instanceof Error ? e.message : 'Failed to update stars');
        }
    };

    let pageFlipRef: any;

    const handlePageChange = (newPage: number) => {
        if (!pageFlipRef) return;

        if (newPage > currentPage()) {
            pageFlipRef.flipNext();
        } else {
            pageFlipRef.flipPrev();
        }
        console.log(newPage)
        setCurrentPage(newPage);
    };

    return (
        <div class="w-full max-w-[1600px] mx-auto px-4 lg:px-12 flex justify-center">
            <Show when={error()}>
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    {error()}
                </div>
            </Show>

            <Show
                when={!book.loading && book()}
                fallback={
                    <div class="text-center py-8">
                        Loading book...
                    </div>
                }
            >
                <BookSpread
                    pages={getPages()}
                    coverImage={getCoverImage()}
                    pageImages={getPageImages()}
                    onPageFlipInit={ref => (pageFlipRef = ref)}
                    onPageChange={setCurrentPage}
                    bookId={book()?.id}
                    stars={book()?.stars || 0}
                    onUpvote={handleUpvote}
                />
            </Show>
        </div>
    );
}