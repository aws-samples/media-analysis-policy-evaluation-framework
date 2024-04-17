function ConvertUtcToLocal(utcTimestamp) {
  const utcDate = new Date(utcTimestamp);
  const localTimestamp = utcDate.toLocaleString();

  return localTimestamp;
}

function CalculateTimeDifference(targetEpoch) {
  const currentEpoch = Math.floor(Date.now() / 1000); // Current epoch time in seconds

  const timeDifference = currentEpoch - targetEpoch;

  const days = Math.floor(timeDifference / (60 * 60 * 24));
  const hours = Math.floor((timeDifference % (60 * 60 * 24)) / (60 * 60));
  const minutes = Math.floor((timeDifference % (60 * 60)) / 60);
  const seconds = Math.floor((timeDifference % (60)));

  let result = "";
  if (days > 0)
    result = `${days} days, `
  if (result.length > 0 || hours > 0)
    result = result + `${hours} hours, `
  if (result.length > 0 || minutes > 0)
    result = result + `${minutes} minutes, `
  if (result.length > 0 || seconds > 0)
    result = result + `${seconds} seconds`
  return result + ' ago';
}

function DecimalToTimestamp(decimalSeconds) {
  if (decimalSeconds === undefined || decimalSeconds === null || decimalSeconds < 0) return "";
  
  const hours = Math.floor(decimalSeconds / 3600);
  const minutes = Math.floor((decimalSeconds % 3600) / 60);
  const seconds = Math.floor(decimalSeconds % 60);
  const milliseconds = Math.round((decimalSeconds % 1) * 1000);

  const formattedHours = hours.toString().padStart(2, '0');
  const formattedMinutes = minutes.toString().padStart(2, '0');
  const formattedSeconds = seconds.toString().padStart(2, '0');
  const formattedMilliseconds = milliseconds.toString().padStart(3, '0');

  return `${formattedHours}:${formattedMinutes}:${formattedSeconds}.${formattedMilliseconds}`;
}

function FormatSeconds(seconds) {
  seconds = parseInt(seconds);
  var hours = Math.floor(seconds / 3600);
  var minutes = Math.floor((seconds % 3600) / 60);
  var remainingSeconds = seconds % 60;

  var result = '';
  if (hours > 0) {
      result += hours + ' hour' + (hours > 1 ? 's' : '') + ', ';
  }
  if (minutes > 0) {
      result += minutes + ' minute' + (minutes > 1 ? 's' : '') + ', ';
  }
  if (remainingSeconds > 0) {
      result += remainingSeconds + ' second' + (remainingSeconds > 1 ? 's' : '');
  }

  return result;
}

function CombineAndDedupArrays(...arrays) {
  // Merge arrays
  const combinedArray = [].concat(...arrays);
  
  // Convert the combined array to a Set to remove duplicates
  const uniqueArray = [...new Set(combinedArray)];
  
  return uniqueArray;
}

export {ConvertUtcToLocal, CalculateTimeDifference, DecimalToTimestamp, FormatSeconds, CombineAndDedupArrays};