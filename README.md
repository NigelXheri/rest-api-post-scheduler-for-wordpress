

### TODOS
- [x] Next time, you will need to find the video from the scheduled videos from the YouTube API by searching the date in the title (for example: "4 tetor") and then use the YouTube video title for the final post title. That is so that the capitalization of the Title is correct because the PDF doesn't contain that information. 
- [x] Handle photo search, upload and compression as featured images
- [x partly] Also, the block tags should be added to the content so that it doens't need to later be converted.
- [ ] Make it check for existing schedulings and only schedule posts that have their videos already uploaded, starting from next day's date
- [ ] Bulk poster for unscheduled posts
- [x] Auto generate footnote tags and ids

## Using `batch_schedule.py`
### Start where the calendar says we are today, go until videos run out
python batch_schedule.py tfl.pdf

### Reproduce an existing run from the known anchor
python batch_schedule.py tfl.pdf --start-date 2026-10-13

### Dry-ish: only do the next 3 pages, with a pause between them
python batch_schedule.py tfl.pdf --start-page 294 --max-pages 3 --sleep 2